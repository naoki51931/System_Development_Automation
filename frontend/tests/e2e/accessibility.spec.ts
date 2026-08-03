import AxeBuilder from"@axe-core/playwright";import{test,expect}from"@playwright/test";
for(const path of ["/login","/","/projects","/projects/00000000-0000-0000-0000-000000000001","/estimates","/contracts","/artifacts","/reviews","/chat","/ai-settings","/users","/dead-letters"]){
 test(`no serious accessibility violations ${path}`,async({page})=>{await page.goto(path);await page.waitForLoadState("networkidle");const result=await new AxeBuilder({page}).analyze();expect(result.violations.filter(x=>["critical","serious"].includes(x.impact||""))).toEqual([])})
}
