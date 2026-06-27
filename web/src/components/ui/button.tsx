import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-[var(--tc-panel-radius)] border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all duration-[var(--tc-duration-fast)] outline-none select-none focus-visible:border-[var(--tc-workspace-focus)] focus-visible:ring-2 focus-visible:ring-[var(--tc-aurora-line)] active:not-aria-[haspopup]:translate-y-px disabled:cursor-not-allowed disabled:opacity-55 aria-invalid:border-[var(--tc-danger-border)] aria-invalid:ring-2 aria-invalid:ring-[var(--tc-danger-border)] [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--tc-workspace-focus)] text-[var(--tc-workspace-shell)] hover:bg-[var(--tc-void-frame-warm)]",
        outline:
          "border-[var(--tc-workspace-border)] bg-transparent text-[var(--tc-workspace-text)] hover:bg-[var(--tc-workspace-panel-soft)] aria-expanded:bg-[var(--tc-workspace-panel-soft)]",
        secondary:
          "border-[var(--tc-workspace-border-weak)] bg-[var(--tc-workspace-panel-soft)] text-[var(--tc-workspace-text)] hover:bg-[color-mix(in_srgb,var(--tc-workspace-panel-soft),var(--tc-workspace-focus)_6%)] aria-expanded:bg-[var(--tc-workspace-panel-soft)]",
        ghost:
          "text-[var(--tc-workspace-text-secondary)] hover:bg-[var(--tc-workspace-panel-soft)] hover:text-[var(--tc-workspace-focus)] aria-expanded:bg-[var(--tc-workspace-panel-soft)]",
        destructive:
          "border-[var(--tc-danger-border)] bg-[var(--tc-danger-soft)] text-[var(--tc-danger-text)] hover:bg-[rgba(240,166,155,0.16)] focus-visible:border-[var(--tc-danger-border)] focus-visible:ring-[var(--tc-danger-border)]",
        link: "text-[var(--tc-workspace-focus)] underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
