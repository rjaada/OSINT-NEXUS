import Link from "next/link"

export default function ArabicHomePage() {
  return (
    <main dir="rtl" className="min-h-screen bg-background text-foreground px-6 py-8 md:px-10">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <p className="text-[11px] uppercase tracking-[0.2em] text-osint-blue mb-2">OSINT NEXUS AR</p>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">مركز العمليات</h1>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            واجهة عربية لمتابعة الأحداث المباشرة، تقييم الإنذارات، وربط الأخبار العاجلة مع التحليل الذكي.
          </p>
        </header>

        <section className="grid md:grid-cols-2 gap-4">
          <Link
            href="/ar/operations"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-green mb-2">مباشر</p>
            <h2 className="text-xl font-semibold mb-2">لوحة العمليات</h2>
            <p className="text-sm text-muted-foreground">
              خريطة مباشرة، تدفق أحداث، وتحديثات مستمرة من المصادر المفتوحة.
            </p>
          </Link>

          <Link
            href="/ar/alerts"
            className="rounded-xl p-6 transition-all hover:bg-white/[0.03]"
            style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-amber mb-2">تنبيهات</p>
            <h2 className="text-xl font-semibold mb-2">ثقة المصادر ووقت الوصول</h2>
            <p className="text-sm text-muted-foreground">
              عرض سريع للتنبيهات عالية الأهمية مع درجة الثقة وتقدير زمني استرشادي.
            </p>
          </Link>
        </section>
      </div>
    </main>
  )
}
