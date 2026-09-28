import { Check, Link2, Printer } from "lucide-react";
import { useState } from "react";

export function ResultActions() {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
    } catch {
      // Clipboard access can be refused (e.g. plain http on another host); let the user copy by hand.
      window.prompt("Bağlantıyı kopyalayın:", window.location.href);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };
  return <div className="result-actions">
    <button className="secondary-button" onClick={copy}>{copied ? <Check size={16} /> : <Link2 size={16} />}{copied ? "Bağlantı kopyalandı" : "Bağlantıyı kopyala"}</button>
    <button className="secondary-button" onClick={() => window.print()}><Printer size={16} />PDF olarak kaydet</button>
  </div>;
}
