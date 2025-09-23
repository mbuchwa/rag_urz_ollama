import React from 'react'

export default function ThinkingSidebar({ think }: { think: string }) {
  return (
    <div className="sidebar h-[70vh] flex flex-col">
      <h3 className="font-semibold mb-2">Model Thinking</h3>
      <pre className="whitespace-pre-wrap text-sm overflow-y-auto flex-1 font-sans">{think}</pre>
    </div>
  )
}
