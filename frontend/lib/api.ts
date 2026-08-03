export type ApiErrorCode = "UNAUTHENTICATED"|"FORBIDDEN"|"VERSION_CONFLICT"|"VALIDATION"|"PROVIDER_UNAVAILABLE"|"UNKNOWN";
export class ApiError extends Error { constructor(public status:number, public code:ApiErrorCode, message:string){super(message)} }
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
function csrf(){return document.cookie.split("; ").find(x=>x.startsWith("sn_csrf="))?.split("=")[1] || ""}
export async function api<T>(path:string, init:RequestInit={}):Promise<T>{
 const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),10000);
 try {const response=await fetch(`${BASE}${path}`,{...init,credentials:"include",cache:"no-store",signal:controller.signal,headers:{"Content-Type":"application/json","X-CSRF-Token":csrf(),...init.headers}});
 if(!response.ok){const safe:{error?:{code?:string;message?:string};detail?:unknown}=await response.json().catch(()=>({})); const map:Record<number,ApiErrorCode>={401:"UNAUTHENTICATED",403:"FORBIDDEN",409:"VERSION_CONFLICT",422:"VALIDATION",503:"PROVIDER_UNAVAILABLE"}; throw new ApiError(response.status,map[response.status]||"UNKNOWN",response.status===409?"別のユーザーにより更新されました。最新情報を読み込み直してください。":safe.error?.message||"処理を完了できませんでした。");}
 return response.status===204?undefined as T:response.json();} finally{clearTimeout(timer)}
}
