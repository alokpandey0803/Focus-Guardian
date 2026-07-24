// Shared between content.js and options.js

const DEFAULT_KEYWORDS = [
  "porn", "pornhub", "xvideos", "xnxx", "xxx", "nsfw",
  "hentai", "onlyfans", "redtube", "youporn", "brazzers",
  "xhamster", "spankbang", "chaturbate", "livejasmin",
];

const QUOTES = [
  "Your future self is watching — make them proud.",
  "Every distraction you resist is a rep for your willpower.",
  "Champions do what they don't feel like doing.",
  "Success is the sum of small efforts repeated day in and day out.",
  "You didn't come this far to only come this far.",
  "Discipline is choosing between what you want now and what you want most.",
  "The pain of discipline is far less than the pain of regret.",
  "Do it now — your future self will thank you.",
  "Focus on the step in front of you, not the whole staircase.",
  "Great things are done by a series of small things brought together.",
  "Your only limit is your mind. Reset it. Stay focused.",
  "Don't watch the clock — do what it does. Keep going.",
  "A year from now you'll wish you had started today.",
  "One hour of focused work beats five hours of distracted work.",
  "Temporary distractions lead to permanent regrets.",
  "You are closer than you think. Keep pushing.",
  "Motivation gets you started — discipline keeps you going.",
  "Every expert was once a beginner who refused to give up.",
  "The secret of getting ahead is getting started — right now.",
  "Be stronger than your excuses.",
  "Hard work beats talent when talent doesn't work hard.",
  "You've got this. Close the tab and get back to work.",
  "Distractions are expensive — pay attention to what matters.",
  "Success requires sacrifice. This is your sacrifice moment.",
  "Stay locked in. The world can wait.",
];

function randomQuote() {
  return QUOTES[Math.floor(Math.random() * QUOTES.length)];
}
