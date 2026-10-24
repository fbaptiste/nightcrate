"""Fixed Markdown copy for the weather methodology endpoint."""

# ruff: noqa: E501 -- fixed user-facing GFM table rows cannot be wrapped.

METHODOLOGY_SUMMARY = """\
NightCrate tells you whether each night offers enough imaging time under your rules.

**Usable time is dark time that meets your enabled hourly limits.**

| Verdict | Meaning |
|---|---|
| **Go** | The forecast supports your session. |
| **Uncertain** | Only with “Show Uncertain”: forecasts disagree about whether, or when, your session will work. |
| **No** | Your rules rule out the session. |
| **Not enough data** | Information needed for a decision is missing or too old. |
| **Night over** | Darkness or your chosen imaging time has ended. |

It checks **darkness, cloud and precipitation**, plus **wind, dew and the Moon** when enabled. Choose enough usable time across the night or one uninterrupted stretch.

**Cloud** comes from up to three forecasts (ECMWF, GFS and ICON). By default, each hour follows the majority.

**Your rules are saved separately for each location.**

> **Tip:** Open a night to see why it received its verdict and set your actual gear and imaging times.
"""

METHODOLOGY_DETAILS = """\
### Which hours count

- Only dark minutes inside your imaging times count, including partial hours.
- **Required darkness:** Astronomical is the darkest setting. Nautical and Civil allow progressively more twilight. If your chosen darkness never occurs, the night is **No**.
- **All night:** Meet both your minimum usable percentage and minimum hours. You can also limit the longest interruption, including time lost at the start or end.
- **Short session:** Require one uninterrupted usable stretch lasting at least your chosen number of hours.
- **Times for one night:** Open its details. With “The whole night is off,” imaging stays within your gear-out times and can be shortened further. With “Only those hours are lost,” only imaging times apply.
- **A night under way:** Only the remaining time counts. Your minimum required hours stay the same.

### Cloud

- Each forecast passes the cloud check when its **total cloud cover is at or below your maximum**.
- Low, middle and high cloud are shown for information. They do not affect the verdict.

### Precipitation

- **Chance:** Your limit applies to each value from the main forecast. NightCrate does not calculate a probability for the whole night.
- **In North America,** beyond about 36 hours from the forecast’s starting time, one chance describes a six-hour stretch and repeats in each hour.
- **Amount:** Each hour’s amount is checked separately. Above your limit fails; equal passes. A zero limit rejects any positive amount.
- **Amount forecasts:** Choose the main forecast alone or add ECMWF, GFS and ICON amounts within their reach. Your cloud forecast selections do not change this choice.
- **The whole night is off:** Exceeding either precipitation limit while your gear is out makes the night **No**, including before or after imaging.
- **Only those hours are lost:** Exclude the affected dark imaging hours. The remaining time can still meet your session requirements.

### Wind, dew and the Moon

- **Wind:** When enabled, steady wind and gusts must stay at or below their respective limits.
- **Dew:** When enabled, air temperature must stay at least your chosen number of degrees above the dew point.
- **Moon:** When enabled, the Moon must be below the horizon, regardless of its phase or your filter.
- Disabled checks remain visible in night details but do not affect the verdict.

### The weather models

- Choose which cloud forecasts to use; all three are selected by default.
- Your preferred forecast breaks ties; ECMWF is the default.
- A forecast that cannot reach an hour sits out. If your preferred forecast cannot reach it, ties use the first selected forecast that can: ECMWF, GFS, then ICON.
- If none reaches an hour, Open-Meteo’s default forecast is used and named.
- Missing values never count as usable.

| When forecasts differ | What happens |
|---|---|
| **Majority for each hour** — default | Follow the majority cloud result each hour. Disagreement alone does not produce Uncertain. |
| **Show Uncertain** | Conflicting session results, or incompatible usable stretches for a short session, can produce Uncertain. |

### When data is missing or old

- Missing values stay unknown. If missing information prevents a decision, you get **Not enough data**. Known failures can still support **No**.
- If a forecast needed for the verdict is overdue and cannot be refreshed, **No** stays **No**; otherwise the result becomes **Not enough data**. The forecast’s age is shown. **Night over** is unchanged.

### Seeing and transparency

- **Seeing** estimates how atmospheric turbulence may affect image sharpness.
- **Transparency** estimates how readily light passes through the atmosphere.
- Both are approximate and **do not affect the verdict**. A dash means the estimate is unavailable.

### Where the data comes from

- **Weather:** Open-Meteo supplies the weather forecasts and additional water-vapour and aerosol data.
- **Astronomy:** NightCrate calculates the Sun and Moon information using Astropy.
"""
