// Where the e2e stack's services are, from inside its network (compose.e2e.yaml).
export const STUDIO_URL = process.env.STUDIO_URL ?? "http://web:3000";
export const API_URL = process.env.API_URL ?? "http://api:8000";
// The one game e2e/seed.sql adds.
export const SEEDED_GAME = "Houston Texans at Jacksonville Jaguars";
