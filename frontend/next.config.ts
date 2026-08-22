import type { NextConfig } from "next";
const internalApiBase = process.env.INTERNAL_API_BASE_URL;
const config: NextConfig = { output:"standalone", poweredByHeader:false, async rewrites(){return internalApiBase?[{source:"/api/v1/:path*",destination:`${internalApiBase}/api/v1/:path*`}]:[]},async headers(){return [{source:"/:path*",headers:[{key:"X-Frame-Options",value:"DENY"},{key:"X-Content-Type-Options",value:"nosniff"},{key:"Referrer-Policy",value:"same-origin"},{key:"Cache-Control",value:"no-store"},{key:"Content-Security-Policy",value:"default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"}]}]}};
export default config;
