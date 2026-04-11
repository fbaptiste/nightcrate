import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { EasterEggWand } from "@/components/EasterEggWand";

const ASTRO_JOKES = [
  "Astrophotography: the only hobby where you spend $10,000 to take pictures while you sleep",
  "My spouse asked how much my gear costs. I said 'about $500'. Per lens. Per filter. Per...",
  "The three stages of astrophotography: 1) This is amazing! 2) Why is everything so expensive? 3) I need a bigger sensor.",
  "You know you're an astrophotographer when your power bill is from the dew heaters, not the AC",
  "Marriage tip: never convert astrophotography spending to 'number of vacations we could have taken'",
  "I don't have a problem. I can stop buying filters anytime I want.",
  "Normal people: 'Nice night!' — Astrophotographers: 'What's the seeing? What's the transparency? Is the jet stream...'",
  "Astrophotography is 10% imaging and 90% waiting for software to finish processing",
  "My retirement plan is selling my imaging rig. At original price. To someone as delusional as me.",
  "Tell me you're an astrophotographer without telling me you're an astrophotographer: 'I know what a meridian flip is'",
  "I got into this hobby because I like looking at stars. Now I look at histograms.",
  "The most expensive thing about astrophotography isn't the gear. It's the therapy for the weather anxiety.",
  "Step 1: Buy a camera. Step 2: Buy 47 adapters so it connects to the telescope. Step 3: Buy a different camera.",
  "Nothing humbles you quite like seeing what Hubble can do with the same target you spent 40 hours on",
  "Astrophotography forums: where people argue about processing techniques for images they can't take because it's cloudy",
  "My imaging train is longer than some people's telescopes",
  "I told my friend I do astrophotography. They asked to see my photos. I showed them a histogram.",
  "There are two types of astrophotographers: those who have enough data, and liars",
  "My darks library is more organized than my actual life",
  "You haven't truly lived until you've debugged a USB connection at 2am in a field with no phone signal",
  "Budget astrophotography is like jumbo shrimp. It doesn't exist.",
  "I'm not addicted to buying gear. I'm just... expanding my spectral coverage.",
  "The best camera for astrophotography is the next one you're going to buy",
  "PixInsight: because Photoshop was too intuitive and user-friendly",
  "My neighbors think I'm a spy. I have a motorized mount tracking things across the sky.",
  "Astrophotographer math: 'I can totally fit a full-frame sensor, filter wheel, OAG, and focuser in 55mm of back focus'",
  "The first rule of astrophotography club: always talk about astrophotography club. Nobody else will listen.",
  "Roses are red, my wallet is blue, I just bought a new scope and a filter set too",
  "I have more USB cables than friends. And that's fine. The cables are more reliable.",
  "Every astrophotographer has a drawer of adapters that don't quite fit anything",
  "My thermos of coffee has seen more clear skies than I have",
  "There's no such thing as 'enough integration time'. There's just 'sunrise happened again.'",
  "Explaining astrophotography to normal people: 'So you take 300 photos of the same thing and then spend a week combining them'",
  "The hardest part of astrophotography isn't the imaging. It's explaining why you need a second mortgage for it.",
  "I've polar aligned more carefully than I've parked my car",
  "Astrophotography taught me patience. Mostly patience for deliveries of new gear.",
  "My scope has a better view of the universe than I'll ever have of my bank account",
  "The definition of optimism: setting up a 12-hour imaging sequence when there's a 30% cloud forecast",
  "I don't always image, but when I do, the neighbor turns on their floodlight",
  "My autoguider has a steadier hand than my surgeon",
  "Flat frames: the homework of astrophotography. Everyone knows they should. Nobody wants to.",
  "You know your hobby is expensive when 'entry level' starts at $2,000",
  "I've spent more time choosing between a 3nm and 6nm Ha filter than choosing my college major",
  "Astrophotography: where 'good enough' is never good enough, but 'eh, I'll fix it in processing' is a lifestyle",
  "My mount tracks celestial objects more faithfully than I track my New Year's resolutions",
  "My light pollution is someone else's back porch. My narrowband filter is my revenge.",
  "If astrophotography has taught me anything, it's that the universe is beautiful and my bank account is empty",
  "The only thing growing faster than the universe is my equipment wishlist",
  "Astrophotographers don't retire. They just upgrade to a permanent observatory and call it 'the final purchase'.",
  "I used to think 'RGB' was simple. Then I learned about LRGB, SHO, HOO, HaRGB, and whatever HOO-Modified is.",
  "That moment when you realize your guide camera costs more than your first car",
  "Sleep is just unguided time between imaging sessions",
  "I don't need therapy. I need 3 arcsecond seeing and a moonless night.",
  "They said 'get a hobby.' They didn't say 'get a hobby that requires its own electrical subpanel.'",
  "I am become astrophotographer, destroyer of savings",
  "My dew heater draws more power than my refrigerator. Priorities.",
  "Objects I've successfully photographed: 47. Objects I've purchased gear to photograph: 47,000.",
  "My significant other: 'What's that box?' Me: 'A filter.' 'Didn't you just get a filter?' 'Different wavelength.'",
  "The five stages of astrophotography grief: denial, anger, bargaining with the weather, depression, acceptance (of the credit card bill)",
  "I'm pretty sure my mount knows when I'm not looking. That's when it decides to lose guide lock.",
  "Stacking 300 subs doesn't make a masterpiece. But it does make you feel like you accomplished something.",
  "Astronomy taught me the universe is vast and mostly empty. Like my ssd after a long imaging night.",
  "My gear bag is a TARDIS. It's bigger on the inside. And more expensive.",
  "If I had a dollar for every photon I've captured, I still couldn't afford another filter.",
  "I showed my astrophoto to a non-astronomer. They said 'nice blob.' I said 'that blob is 2.5 million light years away.' They said 'nice distant blob.'",
  "Astrophotography is like golf: incredibly frustrating, absurdly expensive, and you keep coming back for that one perfect shot",
  "I don't have a problem with gear acquisition syndrome. I can stop anytime. Right after this next camera.",
  "My desktop wallpaper is M42. Not my M42. Someone else's M42. Mine looks like a sneeze.",
  "I calibrate my flats more carefully than I calibrate my life choices",
  "The real deep sky object is the debt I accumulated along the way",
  "Fun fact: the light from Andromeda has been traveling for 2.5 million years just so I can slightly overprocess it",
  "There are two seasons in astrophotography: galaxy season and 'I guess I'll image nebulae again'",
  "NightCrate: organizing the chaos so you can focus on creating more chaos",
  "You're not hoarding equipment. You're curating an observatory.",
  "My cat just walked across my laptop and rejected more subs than Blink ever has",
];

export function HomePage() {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 2, p: 4 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="h4" fontWeight={600}>Welcome to NightCrate</Typography>
        <EasterEggWand lines={ASTRO_JOKES} tooltip="Words of wisdom" size={18} />
      </Box>
      <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 420, textAlign: "center" }}>
        Astrophotography session cataloging and analysis. Use the sidebar to navigate.
      </Typography>
    </Box>
  );
}
