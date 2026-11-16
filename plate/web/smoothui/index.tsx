// SmoothUI Tabs, adapted to Plate’s plain CSS. See LICENSE in this directory.
"use client";

import { Tabs as TabsPrimitive } from "@base-ui/react/tabs";
import { useReducedMotion } from "motion/react";
import {
  type ComponentProps,
  createContext,
  useContext,
  useState,
} from "react";
import {
  activeTabIndicatorStyle,
  composeIndicatorStyle,
  TabsMeasureValueContext,
  useActiveTabIndicatorBox,
} from "./use-active-tab-indicator";

export type TabsVariant = "underline" | "pill" | "segment";

export type TabsRootProps = ComponentProps<typeof TabsPrimitive.Root> & {
  className?: string;
};

export type TabsListProps = ComponentProps<typeof TabsPrimitive.List> & {
  /** Visual style for the list + indicator */
  variant?: TabsVariant;
  className?: string;
};

export type TabsTabProps = ComponentProps<typeof TabsPrimitive.Tab> & {
  className?: string;
};

export type TabsPanelProps = ComponentProps<typeof TabsPrimitive.Panel> & {
  /** Crossfade panels with opacity when true */
  animated?: boolean;
  className?: string;
};

export type TabsIndicatorProps = ComponentProps<
  typeof TabsPrimitive.Indicator
> & {
  className?: string;
};

/** Convenience alias for AutoTypeTable / default root */
export type TabsProps = TabsRootProps;

const TabsVariantContext = createContext<TabsVariant>("underline");

const cn = (...classes: (string | undefined)[]) => classes.filter(Boolean).join(" ");

/**
 * SmoothUI Tabs — Base UI twin (default).
 * Compound: TabsRoot, TabsList (variant), TabsTab, TabsPanel, TabsIndicator.
 */
const TabsRoot = ({
  className,
  value,
  defaultValue,
  onValueChange,
  ...props
}: TabsRootProps) => {
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const current = value === undefined ? uncontrolled : value;

  return (
    <TabsMeasureValueContext.Provider value={current}>
      <TabsPrimitive.Root
        className={className}
        data-slot="tabs"
        defaultValue={defaultValue}
        onValueChange={(next, eventDetails) => {
          if (value === undefined) {
            setUncontrolled(next);
          }
          onValueChange?.(next, eventDetails);
        }}
        value={value}
        {...props}
      />
    </TabsMeasureValueContext.Provider>
  );
};

const TabsList = ({
  className,
  variant = "underline",
  children,
  ...props
}: TabsListProps) => (
  <TabsVariantContext.Provider value={variant}>
    <TabsPrimitive.List
      className={className}
      data-slot="tabs-list"
      data-variant={variant}
      {...props}
    >
      {children}
    </TabsPrimitive.List>
  </TabsVariantContext.Provider>
);

const TabsTab = ({ className, ...props }: TabsTabProps) => {
  return (
    <TabsPrimitive.Tab
      className={className}
      data-slot="tabs-tab"
      {...props}
    />
  );
};

const TabsPanel = ({
  className,
  animated = false,
  ...props
}: TabsPanelProps) => {
  const shouldReduceMotion = useReducedMotion();
  return (
    <TabsPrimitive.Panel
      className={className}
      data-animated={animated && !shouldReduceMotion ? "" : undefined}
      data-slot="tabs-panel"
      {...props}
    />
  );
};

const TabsIndicator = ({ className, style, ...props }: TabsIndicatorProps) => {
  const variant = useContext(TabsVariantContext);
  const shouldReduceMotion = useReducedMotion();
  const { box, ref } = useActiveTabIndicatorBox();
  const measured = activeTabIndicatorStyle(variant, box);

  return (
    <TabsPrimitive.Indicator
      className={cn(shouldReduceMotion ? "reduced-motion" : undefined, className)}
      data-slot="tabs-indicator"
      ref={ref}
      renderBeforeHydration
      style={composeIndicatorStyle(measured, style)}
      {...props}
    />
  );
};

export { TabsIndicator, TabsList, TabsPanel, TabsRoot, TabsTab };

export default TabsRoot;
