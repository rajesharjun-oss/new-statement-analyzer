import { lazy, Suspense, useState } from "react";
import { BarChart3, ChevronDown, FileSpreadsheet, ShieldCheck } from "lucide-react";
import { Badge, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "./components/PrimitiveUI";
import StatementConverter from "./components/StatementConverter";

const AnalysisWorkspace = lazy(() => import("./components/AIAnalysisWorkspace").then((module) => ({
   default: module.AIAnalysisWorkspace,
})));

export default function App() {
   const [workspace, setWorkspace] = useState<"convert" | "analysis">("convert");
   const [openedAnalysis, setOpenedAnalysis] = useState(false);

   return (
      <div className="min-h-screen font-sans text-zinc-300 flex flex-col">
         <header className="sticky top-0 z-50 h-16 border-b border-white/[0.06] bg-[#070707]/90 backdrop-blur-md">
            <div className="mx-auto max-w-[1200px] h-full px-4 sm:px-6 flex items-center justify-between gap-3">
               <button type="button" aria-label="LedgerSentinel home" onClick={() => setWorkspace("convert")} className="flex items-center gap-3 text-left">
                  <span className="w-8 h-8 shrink-0 rounded-full bg-gradient-to-br from-[#9B87FF] to-[#4F85FF] flex items-center justify-center">
                     <ShieldCheck className="w-4 h-4 text-white" aria-hidden="true" />
                  </span>
                  <span className="flex flex-col items-start">
                     <span className="text-[15px] font-bold text-white">LedgerSentinel</span>
                     <Badge variant="purple" className="text-[9px] py-0 px-1 opacity-80">v2.1 STABLE</Badge>
                  </span>
               </button>

               <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                     <button type="button" className="text-[13px] text-zinc-400 font-medium hover:text-white transition-colors flex items-center gap-2">
                        <span className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-[10px] text-white font-bold">IO</span>
                        Account <ChevronDown className="w-3 h-3 opacity-50" aria-hidden="true" />
                     </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                     <DropdownMenuItem>Audit Logs</DropdownMenuItem>
                  </DropdownMenuContent>
               </DropdownMenu>
            </div>
         </header>

         <main className="w-full flex-1 mx-auto max-w-[1200px] px-4 sm:px-6 pt-6 sm:pt-8 pb-12">
            <nav className="statement-workspaces" aria-label="Workspaces">
               <button type="button" aria-pressed={workspace === "convert"} aria-controls="convert-workspace" onClick={() => setWorkspace("convert")}>
                  <FileSpreadsheet size={16} aria-hidden="true" /> PDF to Excel
               </button>
               <button type="button" aria-pressed={workspace === "analysis"} aria-controls="analysis-workspace" onClick={() => {
                  setOpenedAnalysis(true);
                  setWorkspace("analysis");
               }}>
                  <BarChart3 size={16} aria-hidden="true" /> Analysis Workspace
               </button>
            </nav>

            <div id="convert-workspace" hidden={workspace !== "convert"}>
               <StatementConverter />
            </div>
            <div id="analysis-workspace" hidden={workspace !== "analysis"}>
               {openedAnalysis && (
                  <Suspense fallback={<p role="status" className="py-8 text-sm text-zinc-400">Loading analysis workspace...</p>}>
                     <AnalysisWorkspace />
                  </Suspense>
               )}
            </div>
         </main>

         <footer className="w-full py-5 px-4 sm:px-6 mx-auto max-w-[1200px] flex flex-wrap gap-2 justify-between items-center text-[11px] text-zinc-500">
            <span>LedgerSentinel v2.4</span>
            <span>&copy; IBRAHIM ONAWOGA.</span>
         </footer>
      </div>
   );
}
