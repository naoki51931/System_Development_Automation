import {OrganizationProvider} from "@/lib/organization";
import "./globals.css";

export const metadata = {
  title: "SystemNavigator AI",
  description: "AIと人が、システム開発を完成までナビゲート。",
};
export const dynamic = "force-dynamic";

export default function Layout({children}: {children: React.ReactNode}) {
  const mockProviders = [
    process.env.APP_ENABLE_MOCK_AI === "true" && "AI",
    process.env.APP_ENABLE_MOCK_PAYMENT === "true" && "決済",
    process.env.APP_ENABLE_MOCK_EMAIL === "true" && "メール",
  ].filter(Boolean);

  return (
    <html lang="ja">
      <body>
        {mockProviders.length > 0 && (
          <div className="mock-provider-banner" role="status">
            ステージング: Mock Provider使用中（{mockProviders.join(" / ")}）
          </div>
        )}
        <OrganizationProvider>{children}</OrganizationProvider>
      </body>
    </html>
  );
}
