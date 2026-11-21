import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

/** Numbered step of the setup screen, ticked once done. */
export default function Step({ n, done, title, text, children }: {
  n: number; done: boolean; title: string; text: string; children?: React.ReactNode;
}) {
  return (
    <section className="flex gap-4">
      <span aria-hidden className={cn(
        "flex items-center justify-center w-8 h-8 rounded-full shrink-0 text-sm font-bold",
        done ? "bg-primary text-white" : "border-2 border-primary text-brand",
      )}>
        {done ? <Check size={16} /> : n}
      </span>
      <div className="flex-1 min-w-0 space-y-4">
        <div>
          <h2 className="font-heading font-bold text-dark text-lg">
            {title}{done && <span className="sr-only"> (fait)</span>}
          </h2>
          <p className="text-sm text-muted mt-0.5">{text}</p>
        </div>
        {children}
      </div>
    </section>
  );
}
