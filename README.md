# Humor Graph

A Next.js application that renders an interactive "Humor Graph" based on the concept of "Weirdness" vs "Common Understanding". Users can click on the graph to plot themselves and share their position via a unique URL.

## Features

- **Interactive Graph:** Click to place a dot representing yourself or a topic.
- **URL State Sharing:** The graph state is encoded in the URL, making it easy to share your specific configuration with friends without a backend database.
- **Hand-drawn Aesthetic:** Uses SVG and the "Patrick Hand" font to mimic the original whiteboard drawing.
- **Responsive:** Built with Tailwind CSS to look good on all devices.

## Getting Started

First, install dependencies:

```bash
npm install
```

Then, run the development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Ideas for Future Improvements

(As requested by the user)

1.  **Ghost Mode / Backend Integration:** Use a real-time database (like Supabase or Firebase) to show *everyone's* dots simultaneously, perhaps with fading opacity for older dots.
2.  **"The Fall" Animation:** If a user places a dot on the "Cliffs of Insanity", animate it sliding down the slope.
3.  **Categorization:** Allow users to select a category (e.g., "Pun", "Dark Humor", "Slapstick") which changes the color of the dot.
4.  **Comparison Mode:** Overlay a "standard" curve or a friend's curve to compare humor styles.
5.  **Gamification:** A "Humor Quiz" that automatically places you on the graph based on your answers.

## Tech Stack

- Next.js (App Router)
- Tailwind CSS
- Lucide React
- TypeScript
