use serde_json::Value;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Manager, State};

#[derive(Clone, Debug)]
pub enum Mode {
    Off,
    Fresh(String),
    Configured,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase {
    Off,
    Wizard,
    Shell,
    Complete,
}

pub struct SelfTest {
    mode: Mode,
    phase: Mutex<Phase>,
}

impl SelfTest {
    pub fn new(mode: Mode) -> Self {
        let phase = match mode {
            Mode::Off => Phase::Off,
            Mode::Fresh(_) => Phase::Wizard,
            Mode::Configured => Phase::Shell,
        };
        Self {
            mode,
            phase: Mutex::new(phase),
        }
    }

    pub fn enabled(&self) -> bool {
        !matches!(self.mode, Mode::Off)
    }

    pub fn script(&self) -> Option<String> {
        match *self.phase.lock().unwrap() {
            Phase::Wizard => {
                let Mode::Fresh(workspace) = &self.mode else {
                    return None;
                };
                let workspace = serde_json::to_string(workspace).unwrap();
                Some(format!(
                    r#"(async()=>{{try{{
                      const until=Date.now()+60000;
                      while(Date.now()<until&&!document.body.innerText.includes('Welcome to NightCrate')){{await new Promise(r=>setTimeout(r,100));}}
                      if(!document.body.innerText.includes('Welcome to NightCrate'))throw new Error('wizard not shown');
                      const response=await fetch('/api/admin/database/setup',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{path:{workspace},name:'Self-test'}})}});
                      if(!response.ok)throw new Error(`setup failed ${{response.status}}: ${{await response.text()}}`);
                      await window.__TAURI__.core.invoke('selftest_report',{{report:{{phase:'wizard',ok:true}}}});
                    }}catch(error){{await window.__TAURI__.core.invoke('selftest_report',{{report:{{phase:'wizard',ok:false,error:String(error)}}}});}}}})();"#
                ))
            }
            Phase::Shell => Some(
                r#"(async()=>{try{
                  const health=await (await fetch('/api/health')).json();
                  const until=Date.now()+60000;
                  while(Date.now()<until&&!document.body.innerText.includes('v'+health.version)){await new Promise(r=>setTimeout(r,100));}
                  const shell=document.body.innerText.includes('v'+health.version);
                  const assetScript=performance.getEntriesByType('resource').some(entry=>entry.initiatorType==='script'&&new URL(entry.name).pathname.startsWith('/assets/'));
                  await window.__TAURI__.core.invoke('selftest_report',{report:{phase:'shell',ok:shell&&assetScript,shell,assetScript,tauri:!!window.__TAURI__,version:health.version}});
                }catch(error){await window.__TAURI__.core.invoke('selftest_report',{report:{phase:'shell',ok:false,error:String(error)}});}})();"#
                    .to_owned(),
            ),
            _ => None,
        }
    }

    pub fn start_timeout(app: AppHandle) {
        thread::spawn(move || {
            thread::sleep(Duration::from_secs(120));
            let test = app.state::<SelfTest>();
            if test.enabled() && *test.phase.lock().unwrap() != Phase::Complete {
                eprintln!("[selftest] timed out waiting for the next report");
                app.exit(2);
            }
        });
    }
}

#[tauri::command]
pub fn selftest_report(app: AppHandle, test: State<'_, SelfTest>, report: Value) {
    let phase = report.get("phase").and_then(Value::as_str);
    let ok = report.get("ok").and_then(Value::as_bool).unwrap_or(false);
    let mut current = test.phase.lock().unwrap();
    match (*current, phase, ok) {
        (Phase::Wizard, Some("wizard"), true) => {
            *current = Phase::Shell;
            drop(current);
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.eval("window.location.reload()");
            }
        }
        (Phase::Shell, Some("shell"), true)
            if report.get("shell").and_then(Value::as_bool) == Some(true)
                && report.get("tauri").and_then(Value::as_bool) == Some(true)
                && report.get("version").and_then(Value::as_str)
                    == Some(app.package_info().version.to_string().as_str()) =>
        {
            *current = Phase::Complete;
            drop(current);
            app.exit(0);
        }
        _ => {
            eprintln!("[selftest] failed report: {report}");
            *current = Phase::Complete;
            drop(current);
            app.exit(1);
        }
    }
}
