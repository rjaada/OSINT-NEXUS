"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

export default function ArabicHomePage() {
  const [role, setRole] = useState("viewer")
  const [user, setUser] = useState("user")

  useEffect(() => {
    const roleCookie = document.cookie.split("; ").find((x) => x.startsWith("osint_role="))
    const userCookie = document.cookie.split("; ").find((x) => x.startsWith("osint_user="))
    setRole(roleCookie ? decodeURIComponent(roleCookie.split("=")[1]).toLowerCase() : "viewer")
    setUser(userCookie ? decodeURIComponent(userCookie.split("=")[1]) : "user")
  }, [])

  const logout = async () => {
    try {
      await fetch("http://localhost:8000/api/auth/logout", { method: "POST", credentials: "include" })
    } catch (_) {}
    document.cookie = "osint_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax"
    document.cookie = "osint_role=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax"
    document.cookie = "osint_user=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax"
    window.location.href = "/login"
  }

  return (
    <main dir="rtl" className="min-h-screen bg-background text-foreground px-6 py-8 md:px-10">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <div className="flex items-center justify-start mb-3 gap-2">
            <span className="text-[10px] tracking-[0.14em] uppercase px-3 py-1.5 rounded" style={{ color: "#00b4d8", border: "1px solid #00b4d855", background: "#00b4d818" }}>
              {user} · {role}
            </span>
            <button onClick={logout} className="text-[10px] tracking-[0.14em] uppercase px-3 py-1.5 rounded" style={{ color: "#ff1a3c", border: "1px solid #ff1a3c55", background: "#ff1a3c18" }}>
              خروج
            </button>
            <Link
              href="/ar"
              className="text-[10px] tracking-[0.14em] uppercase px-3 py-1.5 rounded"
              style={{ color: "#00ff88", border: "1px solid #00ff8855", background: "#00ff8818" }}
            >
              v1 المستقر
            </Link>
          </div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-osint-blue mb-2">OSINT NEXUS AR</p>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">مركز المهام</h1>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            واجهات مستقلة للعمليات المباشرة، تقييم الإنذارات، والتحقق من المصادر لتقليل التشويش أثناء التصعيد.
          </p>
        </header>

        <section className="grid md:grid-cols-4 gap-4">
          <Link
            href="/v2/ar/operations"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-green mb-2">مباشر</p>
            <h2 className="text-xl font-semibold mb-2">لوحة العمليات</h2>
            <p className="text-sm text-muted-foreground">خريطة مباشرة، تدفق أحداث، وتحديثات لحظية.</p>
          </Link>

          <Link
            href="/v2/ar/alerts"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-amber mb-2">إنذارات</p>
            <h2 className="text-xl font-semibold mb-2">الثقة والتقدير الزمني</h2>
            <p className="text-sm text-muted-foreground">قرار أسرع مع تفسير سبب الثقة لكل تنبيه.</p>
          </Link>

          <Link
            href="/v2/ar/sources"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-blue mb-2">المصادر</p>
            <h2 className="text-xl font-semibold mb-2">مكتب التحقق والصحة التشغيلية</h2>
            <p className="text-sm text-muted-foreground">عرض المصدر الخام + مؤشرات الصحة والمراقبة.</p>
          </Link>

          <Link
            href="/v2/ar/health"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-purple mb-2">تشغيل</p>
            <h2 className="text-xl font-semibold mb-2">لوحة الصحة</h2>
            <p className="text-sm text-muted-foreground">مراقبة الطوابير والمراقب واتصال PostgreSQL ضمن مرحلة 2.</p>
          </Link>

          {role === "admin" ? (
            <Link
              href="/v2/ar/admin"
              className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
              style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
            >
              <p className="text-[10px] tracking-[0.18em] uppercase text-osint-purple mb-2">الصلاحيات</p>
              <h2 className="text-xl font-semibold mb-2">إدارة المستخدمين</h2>
              <p className="text-sm text-muted-foreground">ترقية أو خفض الأدوار مع حماية آخر حساب مشرف.</p>
            </Link>
          ) : null}
        </section>
      </div>
    </main>
  )
}
