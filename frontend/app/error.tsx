"use client";export default function Error({reset}:{reset:()=>void}){return <main><h1>エラー</h1><p role="alert">画面を表示できませんでした。</p><button onClick={reset}>再試行</button></main>}
