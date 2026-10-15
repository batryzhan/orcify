import { clsx, type ClassValue } from "clsx";
import { cva, type VariantProps } from "class-variance-authority";
import { twMerge } from "tailwind-merge";
import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

export function cn(...values: ClassValue[]): string {
  return twMerge(clsx(values));
}

const buttonVariants = cva("button", {
  variants: {
    variant: {
      primary: "button-primary",
      secondary: "button-secondary",
      ghost: "button-ghost",
    },
  },
  defaultVariants: { variant: "primary" },
});

export function Button({
  children,
  className,
  variant,
  ...props
}: PropsWithChildren<
  ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>
>) {
  return (
    <button className={cn(buttonVariants({ variant }), className)} {...props}>
      {children}
    </button>
  );
}

export function Badge({
  children,
  className,
}: PropsWithChildren<{ className?: string }>) {
  return (
    <span
      className={cn(
        "badge inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[9px] font-semibold",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function SectionLabel({ children }: PropsWithChildren) {
  return <div className="section-label">{children}</div>;
}
