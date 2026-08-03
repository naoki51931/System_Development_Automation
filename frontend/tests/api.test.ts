import{afterEach,describe,expect,it,vi}from"vitest";
import{api,ApiError,API_BASE}from"../lib/api";

afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();document.cookie="sn_csrf=; Max-Age=0"});

function response(status:number,body:unknown={}){return{ok:status>=200&&status<300,status,json:vi.fn().mockResolvedValue(body)}}

describe("API client security and error contract",()=>{
  it("sends HttpOnly-session credentials, CSRF, and no-store",async()=>{document.cookie="sn_csrf=csrf%20value";const fetch=vi.fn().mockResolvedValue(response(200,{id:"1"}));vi.stubGlobal("fetch",fetch);await expect(api("/projects")).resolves.toEqual({id:"1"});expect(fetch).toHaveBeenCalledWith(`${API_BASE}/projects`,expect.objectContaining({credentials:"include",cache:"no-store",headers:expect.objectContaining({"X-CSRF-Token":"csrf value"})}))});
  it.each([[401,"UNAUTHENTICATED","ログインが必要です。"],[403,"FORBIDDEN","権限"],[404,"NOT_FOUND","見つかりません"],[409,"VERSION_CONFLICT","別のユーザー"],[422,"VALIDATION","入力内容"],[503,"PROVIDER_UNAVAILABLE","一時的"]] as const)("maps %i without exposing details",async(status,code,message)=>{vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(status,{detail:"secret SQL"})));await expect(api("/x")).rejects.toMatchObject({status,code,message:expect.stringContaining(message)})});
  it("maps unknown errors to a sanitized message",async()=>{vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(500,{error:{message:"safe"}})));await expect(api("/x")).rejects.toEqual(new ApiError(500,"UNKNOWN","safe"))});
  it("returns undefined for 204",async()=>{vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(204)));await expect(api("/x")).resolves.toBeUndefined()});
  it("maps network failure",async()=>{vi.stubGlobal("fetch",vi.fn().mockRejectedValue(new Error("socket secret")));await expect(api("/x")).rejects.toMatchObject({status:503,code:"PROVIDER_UNAVAILABLE",message:"APIへ接続できませんでした。"})});
  it("maps timeout and clears its timer",async()=>{vi.useFakeTimers();vi.stubGlobal("fetch",vi.fn((_u,_i)=>new Promise((_resolve,reject)=>{(_i as RequestInit).signal?.addEventListener("abort",()=>reject(Object.assign(new Error("abort"),{name:"AbortError"}))) })));const assertion=expect(api("/slow")).rejects.toMatchObject({status:503,message:"応答がタイムアウトしました。"});await vi.advanceTimersByTimeAsync(10001);await assertion});
  it("renders XSS input as text, never HTML",()=>{const value='<img src=x onerror="alert(1)">';const node=document.createElement("p");node.textContent=value;expect(node.querySelector("img")).toBeNull();expect(node.textContent).toBe(value)})
});
