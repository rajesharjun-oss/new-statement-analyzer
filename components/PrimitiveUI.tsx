import React from 'react';

export function cn(...classes: (string | undefined | null | false)[]) {
  return classes.filter(Boolean).join(' ');
}

// Button - 12px Radius, Primary Accent is soft Purple
export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'outline' | 'ghost' | 'primary' | 'danger', size?: 'default' | 'sm' | 'xs' }>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => {
    const variants = {
      default: "bg-white text-black hover:bg-zinc-200 border border-transparent font-semibold shadow-sm",
      primary: "bg-[#9B87FF] text-[#0E0F12] hover:bg-[#8A76F5] border border-transparent font-bold shadow-[0_4px_12px_rgba(155,135,255,0.15)]",
      outline: "border border-white/10 bg-transparent text-zinc-300 hover:text-white hover:border-white/20 hover:bg-white/5",
      ghost: "text-zinc-500 hover:text-zinc-200 hover:bg-white/5",
      danger: "bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20",
    };
    const sizes = {
      default: "h-11 px-5 py-2 rounded-[12px] text-[14px]", 
      sm: "h-9 px-3 rounded-[10px] text-[13px]",
      xs: "h-7 px-2 rounded-[8px] text-[11px]",
    };
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#9B87FF]/50 disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98]",
          variants[variant as keyof typeof variants] || variants.default,
          sizes[size as keyof typeof sizes] || sizes.default,
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

// Card - Surface #0E0F12, 16px Radius, Very Subtle Border
export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("rounded-[16px] border border-white/[0.08] bg-[#0E0F12] shadow-[0_18px_40px_rgba(0,0,0,0.55)]", className)} {...props} />
));
Card.displayName = "Card";

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
));
CardHeader.displayName = "CardHeader";

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
));
CardContent.displayName = "CardContent";

// Input - Darker bg, flush style
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, type, ...props }, ref) => (
  <input
    type={type}
    className={cn(
      "flex h-10 w-full rounded-[10px] border border-white/10 bg-[#070707] px-3 py-2 text-sm text-zinc-100 shadow-none transition-colors placeholder:text-zinc-600 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#9B87FF] disabled:cursor-not-allowed disabled:opacity-50 font-sans",
      className
    )}
    ref={ref}
    {...props}
  />
));
Input.displayName = "Input";

// Badge - Pill shape, quiet colors
export const Badge = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { variant?: 'default' | 'outline' | 'success' | 'warning' | 'danger' | 'purple' }>(({ className, variant = "default", ...props }, ref) => {
  const variants = {
    default: "bg-white/5 text-zinc-400 border-transparent",
    outline: "border-white/10 text-zinc-500",
    success: "bg-[#3CDCAB]/10 text-[#3CDCAB] border-[#3CDCAB]/20",
    warning: "bg-[#FFB43C]/10 text-[#FFB43C] border-[#FFB43C]/20",
    danger: "bg-[#FF5A78]/10 text-[#FF5A78] border-[#FF5A78]/20",
    purple: "bg-[#9B87FF]/10 text-[#9B87FF] border-[#9B87FF]/20"
  };
  return (
    <div ref={ref} className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium border transition-colors", variants[variant as keyof typeof variants], className)} {...props} />
  );
});
Badge.displayName = "Badge";

// Separator
export const Separator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("shrink-0 bg-white/[0.08] h-[1px] w-full", className)} {...props} />
));
Separator.displayName = "Separator";

// Progress - Slim, Purple Accent
export const Progress = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { value?: number }>(({ className, value, ...props }, ref) => (
  <div ref={ref} className={cn("relative h-1 w-full overflow-hidden rounded-full bg-white/5", className)} {...props}>
    <div className="h-full w-full flex-1 bg-[#9B87FF] transition-all duration-500 ease-out" style={{ transform: `translateX(-${100 - (value || 0)}%)` }} />
  </div>
));
Progress.displayName = "Progress";

// Dropdown
export const DropdownMenu = ({ children }: any) => <div className="relative inline-block text-left group z-40">{children}</div>;
export const DropdownMenuTrigger = ({ asChild, children }: any) => <div className="cursor-pointer">{children}</div>;
export const DropdownMenuContent = ({ className, children }: any) => (
  <div className={cn("hidden group-hover:block absolute right-0 top-full mt-2 w-56 origin-top-right rounded-[14px] bg-[#111318] border border-white/10 shadow-[0_10px_30px_rgba(0,0,0,0.5)] z-50 p-1.5", className)}>
    {children}
  </div>
);
export const DropdownMenuItem = ({ children, onClick }: any) => (
  <button onClick={onClick} className="block w-full text-left px-3 py-2 text-[13px] font-medium text-zinc-400 rounded-[8px] hover:bg-white/5 hover:text-white transition-colors">
    {children}
  </button>
);