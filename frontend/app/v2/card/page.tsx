"use client"

import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"
import { OperatorAccessCard } from "@/components/auth/operator-access-card"

export default function V2CardPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />
      <OperatorAccessCard displayOnly />
    </div>
  )
}
