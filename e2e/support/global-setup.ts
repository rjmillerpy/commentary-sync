import { writeToneFile } from "./tone";

/** Runs once, before any browser starts: the fake microphone's file must exist. */
export default function globalSetup(): void {
  writeToneFile();
}
