import Studio from "@/components/Studio";
import { SessionProvider } from "@/hooks/useSession";

export default function StudioPage() {
  return (
    <main>
      <h1>Studio</h1>
      <SessionProvider>
        <Studio />
      </SessionProvider>
    </main>
  );
}
