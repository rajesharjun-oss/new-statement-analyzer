
import React from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs'; // Assuming we simulate or use simple state if radix not avail.
// Actually, to avoid deps, I'll build simple controlled components.

export function cn(...classes: (string | undefined | null | false)[]) {
  return classes.filter(Boolean).join(' ');
}

// Button
export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'outline' | 'ghost', size?: 'default' | 'sm' | 'lg' }>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => {
    const variants = {
      default: "bg-white text-zinc-950 hover:bg-white/90 shadow-sm",
      outline: "border border-zinc-200 bg-transparent shadow-sm hover:bg-zinc-100 text-zinc-900 dark:border-white/10 dark:text-white dark:hover:bg-white/10",
      ghost: "hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-white/10 dark:hover:text-white",
    };
    const sizes = {
      default: "h-9 px-4 py-2",
      sm: "h-8 rounded-md px-3 text-xs",
      lg: "h-10 rounded-md px-8",
    };
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-xl text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50",
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

// Card
export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("rounded-xl border bg-card text-card-foreground shadow", className)} {...props} />
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

// Input
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, type, ...props }, ref) => (
  <input
    type={type}
    className={cn(
      "flex h-9 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-950 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:placeholder:text-white/40 dark:focus-visible:ring-white/20",
      className
    )}
    ref={ref}
    {...props}
  />
));
Input.displayName = "Input";

// Badge
export const Badge = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { variant?: 'default' | 'secondary' | 'destructive' | 'outline' }>(({ className, variant = "default", ...props }, ref) => {
  return (
    <div ref={ref} className={cn("inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-950 focus:ring-offset-2", className)} {...props} />
  );
});
Badge.displayName = "Badge";

// Separator
export const Separator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("shrink-0 bg-zinc-200 dark:bg-white/10 h-[1px] w-full", className)} {...props} />
));
Separator.displayName = "Separator";

// Progress
export const Progress = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { value?: number }>(({ className, value, ...props }, ref) => (
  <div ref={ref} className={cn("relative h-2 w-full overflow-hidden rounded-full bg-zinc-900/20 dark:bg-white/10", className)} {...props}>
    <div className="h-full w-full flex-1 bg-zinc-900 transition-all dark:bg-white" style={{ transform: `translateX(-${100 - (value || 0)}%)` }} />
  </div>
));
Progress.displayName = "Progress";

// Tabs (Simple Implementation)
interface TabsContextType {
  value: string;
  onValueChange: (value: string) => void;
}
const TabsContext = React.createContext<TabsContextType | undefined>(undefined);

export const Tabs = ({ defaultValue, value, onValueChange, children, className }: any) => {
  const [activeTab, setActiveTab] = React.useState(value || defaultValue);
  const handleTabChange = (val: string) => {
    setActiveTab(val);
    onValueChange?.(val);
  };
  return (
    <TabsContext.Provider value={{ value: activeTab, onValueChange: handleTabChange }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
};

export const TabsList = ({ className, children }: any) => (
  <div className={cn("inline-flex h-9 items-center justify-center rounded-lg bg-zinc-100 p-1 text-zinc-500 dark:bg-white/5 dark:text-zinc-400", className)}>
    {children}
  </div>
);

export const TabsTrigger = ({ value, className, children }: any) => {
  const context = React.useContext(TabsContext);
  const isActive = context?.value === value;
  return (
    <button
      type="button"
      onClick={() => context?.onValueChange(value)}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium ring-offset-white transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-950 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
        isActive ? "bg-white text-zinc-950 shadow dark:bg-white dark:text-zinc-950" : "hover:text-zinc-900 dark:hover:text-zinc-100",
        className
      )}
    >
      {children}
    </button>
  );
};

export const TabsContent = ({ value, className, children }: any) => {
  const context = React.useContext(TabsContext);
  if (context?.value !== value) return null;
  return <div className={cn("mt-2 ring-offset-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-950 focus-visible:ring-offset-2", className)}>{children}</div>;
};

// Dropdown (Simple Simulation for Layout)
export const DropdownMenu = ({ children }: any) => <div className="relative inline-block text-left group">{children}</div>;
export const DropdownMenuTrigger = ({ asChild, children }: any) => <div className="cursor-pointer">{children}</div>;
export const DropdownMenuContent = ({ className, children }: any) => (
  <div className={cn("hidden group-hover:block absolute right-0 z-50 mt-2 w-56 origin-top-right rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900 dark:border-white/10", className)}>
    <div className="py-1">{children}</div>
  </div>
);
export const DropdownMenuItem = ({ children, onClick }: any) => (
  <button onClick={onClick} className="block w-full text-left px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-white/10">
    {children}
  </button>
);
