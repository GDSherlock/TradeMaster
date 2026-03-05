import { Github, Instagram, Linkedin, Twitter } from "lucide-react";

const columns = {
  Product: ["Platform", "Signals", "Portfolio", "Automation"],
  Company: ["About", "Careers", "Press", "Partners"],
  Support: ["Help center", "Status", "Contact", "Docs"],
  Legal: ["Privacy", "Terms", "Cookies", "Disclosures"]
};

const socials = [
  { label: "Twitter", Icon: Twitter },
  { label: "LinkedIn", Icon: Linkedin },
  { label: "Instagram", Icon: Instagram },
  { label: "GitHub", Icon: Github }
];

export function Footer() {
  return (
    <footer className="mt-20 border-t border-black/10 py-14">
      <div className="section-shell grid gap-10 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <div className="mb-4 flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-ink text-sm font-semibold text-white">CA</span>
            <span className="text-lg font-semibold">Crypto Analyst</span>
          </div>
          <p className="max-w-md text-sm leading-relaxed text-muted">
            A modern crypto intelligence interface for market pulse, signal confidence, portfolio risk tracking, and alerts.
          </p>
          <div className="mt-6 flex items-center gap-2">
            {socials.map(({ label, Icon }) => (
              <a
                key={label}
                href="#"
                aria-label={label}
                className="focus-ring inline-flex rounded-full border border-black/10 p-2 text-muted transition hover:border-black/20 hover:text-ink"
              >
                <Icon size={16} />
              </a>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          {Object.entries(columns).map(([title, items]) => (
            <div key={title}>
              <h3 className="mb-3 text-sm font-semibold text-ink">{title}</h3>
              <ul className="space-y-2 text-sm text-muted">
                {items.map((item) => (
                  <li key={item}>
                    <a href="#" className="focus-ring rounded-sm transition hover:text-ink">
                      {item}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </footer>
  );
}
