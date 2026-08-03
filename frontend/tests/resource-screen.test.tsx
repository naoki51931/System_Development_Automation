import React from"react";import{cleanup,render,screen,waitFor}from"@testing-library/react";import{afterEach,describe,expect,it,vi}from"vitest";
const{api,state}=vi.hoisted(()=>({api:vi.fn(),state:{project:""}}));
vi.mock("../lib/api",()=>({api}));
vi.mock("../lib/organization",()=>({useOrganization:()=>({organizationId:"org-1"}),selectedProject:()=>state.project}));
vi.mock("../components/Shell",()=>({Shell:({children,title}:{children:React.ReactNode;title:string})=><main><h1>{title}</h1>{children}</main>}));
import ResourceScreen from"../features/portal/ResourceScreen";
afterEach(()=>{cleanup();api.mockReset();state.project=""});
describe("resource portal decisions",()=>{
 it("requires a selected project before fetching estimates",async()=>{render(<ResourceScreen section="estimates"/>);expect(await screen.findByRole("status")).toHaveTextContent("案件一覧から対象案件を選択");expect(api).not.toHaveBeenCalled()});
 it("renders a safe 404 for unknown sections",()=>{render(<ResourceScreen section="unknown"/>);expect(screen.getByRole("heading",{name:"404"})).toBeInTheDocument();expect(screen.getByText("ページが見つかりません。")).toBeInTheDocument()});
 it("loads and renders tenant-scoped notifications",async()=>{api.mockResolvedValueOnce({items:[{id:"n1",title:"通知",status:"delivered",version:1}],next_cursor:null});render(<ResourceScreen section="notifications"/>);await waitFor(()=>expect(api).toHaveBeenCalledWith("/notifications?organization_id=org-1"));expect(await screen.findAllByText("通知")).toHaveLength(2)});
 it.each(["contracts","payments","artifacts","reviews","change-requests","ai-settings","maintenance","users","audit-logs","dead-letters"])("loads %s through the shared tenant client",async section=>{api.mockResolvedValue({items:[],next_cursor:null});render(<ResourceScreen section={section}/>);await waitFor(()=>expect(api).toHaveBeenCalled());expect(await screen.findByText("データはありません。")).toBeInTheDocument()});
 it("sends the server version when marking a notification read",async()=>{api.mockResolvedValueOnce({items:[{id:"n1",title:"New",status:"delivered",version:7}],next_cursor:null}).mockResolvedValueOnce({}).mockResolvedValueOnce({items:[],next_cursor:null});render(<ResourceScreen section="notifications"/>);await screen.findByText("New");screen.getByRole("button",{name:"実行"}).click();await waitFor(()=>expect(api).toHaveBeenCalledWith("/notifications/n1/read",{method:"POST",body:JSON.stringify({version:7})}))});
});
