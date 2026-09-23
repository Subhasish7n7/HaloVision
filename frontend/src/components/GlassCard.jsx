import { cn } from "../lib/utils"

export default function GlassCard({ className, children, ...props }) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/10 backdrop-blur-xl bg-white/[0.02] p-6 hover:shadow-[0_0_30px_rgba(255,179,71,0.15)] transition-all duration-500 hover:-translate-y-1",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
