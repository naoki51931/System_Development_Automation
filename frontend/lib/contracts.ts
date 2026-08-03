/** API view models are normalized once here; mutation inputs come from generated OpenAPI components. */
import type {components,paths} from "./generated/api";
export type OpenAPIComponents=components["schemas"];
export type ProjectCreate=OpenAPIComponents["ProjectCreate"];
export type EstimateCreateInput=OpenAPIComponents["EstimateCreateInput"];
export type ChatMessageInput=OpenAPIComponents["ChatMessageInput"];
export type VersionInput=OpenAPIComponents["VersionInput"];
export type GeneratedPath=keyof paths;
export type ApiScalar=string|number|boolean|null;
export type ApiRecord={id?:string;version?:number;[key:string]:ApiScalar|ApiRecord|ApiRecord[]|string[]|undefined};
export type CursorPage<T extends ApiRecord=ApiRecord>={items:T[];next_cursor:string|null};
export type Organization={id:string;name:string;roles?:string[]};
export type CurrentUser={id:string;display_name:string;organizations:Organization[]};
