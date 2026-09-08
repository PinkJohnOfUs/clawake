// Dependency-free native Control UI module for OpenClaw 2026.9.2.
export default {
  id: "pflege-google-limited",
  activate(host) {
    const page = host.ui.registerPage({
      id: "google-account", label: "Google-Konto",
      mount(container, context) {
        const root = document.createElement("section");
        root.style.cssText = "padding:24px;max-width:760px;margin:auto;display:grid;gap:16px";
        const title = document.createElement("h2");
        title.textContent = "Google-Konto";
        const info = document.createElement("p");
        info.textContent = "Verbinde das Google-Konto für Gmail, Kalender und Drive. Die Anmeldung öffnet sich in einem normalen Browser-Tab. Gmail kann gelesen, gesendet und verwaltet werden; Kalendertermine können erstellt und geändert werden. Drive-Metadaten werden nur gelesen.";
        const status = document.createElement("p");
        status.setAttribute("role", "status");
        const callback = document.createElement("code");
        const connect = document.createElement("button");
        connect.textContent = "Google-Konto verbinden";
        connect.disabled = true;
        const refresh = document.createElement("button");
        refresh.textContent = "Status aktualisieren";
        let disposed = false;
        async function update() {
          try {
            const result = await context.host.request("pflege-google.status", {});
            if (disposed) return;
            callback.textContent = `Google-Rückrufadresse: ${result.redirectUri}`;
            connect.disabled = !result.configured || location.origin !== result.origin;
            status.textContent = location.origin !== result.origin
              ? `Bitte das Dashboard unter ${result.origin} öffnen.`
              : !result.configured
                ? "Einrichtung erforderlich: Google-Webclient mit dieser Rückrufadresse als Clientdatei hinterlegen."
                : result.tokenStored
                  ? "Token gespeichert. Seine Gültigkeit wurde nicht bei Google geprüft. Erneutes Verbinden ersetzt die Verbindung nach erfolgreicher Zustimmung."
                  : "Bereit zum Verbinden.";
          } catch {
            if (!disposed) status.textContent = "Status nicht verfügbar. Verbindung und Administratorberechtigung prüfen.";
          }
        }
        connect.onclick = async () => {
          // Open synchronously to avoid popup blocking; never expose OAuth tickets in URLs.
          const target = `pflege-google-${crypto.randomUUID()}`;
          const popup = window.open("about:blank", target);
          if (!popup) { status.textContent = "Bitte Pop-ups für dieses Dashboard erlauben."; return; }
          popup.opener = null;
          connect.disabled = true;
          try {
            const result = await context.host.request("pflege-google.start", { origin: location.origin });
            if (disposed) { popup.close(); return; }
            if (new URL(result.launchUrl).origin !== location.origin) throw new Error("Origin mismatch");
            const form = popup.document.createElement("form");
            form.method = "POST"; form.action = result.launchUrl;
            const ticket = popup.document.createElement("input");
            ticket.type = "hidden"; ticket.name = "ticket"; ticket.value = result.ticket;
            form.append(ticket); popup.document.body.append(form); form.submit();
            status.textContent = "Anmeldung im neuen Tab abschließen, danach hier den Status aktualisieren.";
          } catch {
            popup.close();
            if (!disposed) status.textContent = "Anmeldung konnte nicht gestartet werden. Konfiguration und Administratorberechtigung prüfen.";
          } finally { if (!disposed) connect.disabled = false; }
        };
        refresh.onclick = update;
        root.append(title, info, status, callback, connect, refresh);
        container.append(root);
        void update();
        return { dispose() { disposed = true; root.remove(); } };
      },
    });
    const nav = host.ui.registerNavigation({ id: "google-account", label: "Google-Konto", page: { id: "google-account", path: [] }, order: 30 });
    return () => { nav(); page(); };
  },
};
