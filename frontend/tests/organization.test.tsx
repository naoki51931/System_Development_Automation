import React from"react";import{act,cleanup,render,screen,waitFor}from"@testing-library/react";import{afterEach,describe,expect,it,vi}from"vitest";
const{api}=vi.hoisted(()=>({api:vi.fn()}));vi.mock("../lib/api",()=>({api}));
import{OrganizationProvider,useOrganization,selectedProject}from"../lib/organization";
function Probe(){const value=useOrganization();return <><span>{value.loading?"loading":value.organizationId}</span><button onClick={()=>value.switchOrganization("org-2")}>switch</button></>}
afterEach(()=>{cleanup();api.mockReset();sessionStorage.clear()});
describe("organization boundary",()=>{
 it("restores only a verified membership",async()=>{sessionStorage.setItem("sn.organization","evil");api.mockResolvedValueOnce({display_name:"User",organizations:[{id:"org-1",name:"One"}]});render(<OrganizationProvider><Probe/></OrganizationProvider>);expect(await screen.findByText("org-1")).toBeInTheDocument();expect(sessionStorage.getItem("sn.organization")).toBe("org-1")});
 it("clears tenant-scoped cache after server-authorized switch",async()=>{sessionStorage.setItem("sn.project","project-1");api.mockResolvedValueOnce({display_name:"User",organizations:[{id:"org-1",name:"One"},{id:"org-2",name:"Two"}]}).mockResolvedValueOnce({});render(<OrganizationProvider><Probe/></OrganizationProvider>);await screen.findByText("org-1");await act(async()=>screen.getByRole("button").click());expect(api).toHaveBeenLastCalledWith("/auth/switch-organization",expect.objectContaining({method:"POST",body:JSON.stringify({organization_id:"org-2"})}));expect(sessionStorage.getItem("sn.project")).toBeNull();expect(sessionStorage.getItem("sn.organization")).toBe("org-2")});
 it("finishes loading after a failed current-user request",async()=>{api.mockRejectedValueOnce(new Error("denied"));render(<OrganizationProvider><Probe/></OrganizationProvider>);await waitFor(()=>expect(screen.queryByText("loading")).not.toBeInTheDocument())});
 it("reads selected project only from the current session",()=>{sessionStorage.setItem("sn.project","p1");expect(selectedProject()).toBe("p1")})
});
