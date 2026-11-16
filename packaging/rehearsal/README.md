# Update rehearsal

`update-rehearsal.yml` builds disposable versions 0.0.1 and 0.0.2 with a
throwaway updater key. The harness provisions a private workspace through the
frozen backend, verifies that a wrong signature leaves 0.0.1 running, then
installs 0.0.2 and checks the workspace, backup, relationships, source image,
integrity, foreign keys, and upgrade-marker cleanup.

All servers bind to `127.0.0.1`; all app data and keys live under the runner's
temporary directory. The workflow never uses the production updater key.
