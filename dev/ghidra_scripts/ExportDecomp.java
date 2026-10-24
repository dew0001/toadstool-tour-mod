// Export every function's decompiled C plus a function index.
// Args: <output directory>
// Writes decomp.c (all functions, address-ordered) and functions.tsv.
// @category TKToadstool
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

public class ExportDecomp extends GhidraScript {
	@Override
	public void run() throws Exception {
		File out = new File(getScriptArgs()[0]);
		out.mkdirs();
		DecompInterface di = new DecompInterface();
		di.openProgram(currentProgram);
		int total = 0;
		int failed = 0;
		try (PrintWriter c = new PrintWriter(new FileWriter(new File(out, "decomp.c")));
				PrintWriter t = new PrintWriter(new FileWriter(new File(out, "functions.tsv")))) {
			t.println("address\tname\tsize\tcallers\tcallees");
			FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
			while (it.hasNext() && !monitor.isCancelled()) {
				Function f = it.next();
				t.printf("%s\t%s\t%d\t%d\t%d%n", f.getEntryPoint(), f.getName(),
					f.getBody().getNumAddresses(), f.getCallingFunctions(monitor).size(),
					f.getCalledFunctions(monitor).size());
				c.println("// ==== " + f.getEntryPoint() + " " + f.getName());
				DecompileResults r = di.decompileFunction(f, 60, monitor);
				if (r != null && r.decompileCompleted()) {
					c.println(r.getDecompiledFunction().getC());
				}
				else {
					c.println("// decompile failed: " + (r == null ? "null" : r.getErrorMessage()));
					failed++;
				}
				total++;
			}
		}
		di.dispose();
		println("Exported " + total + " functions (" + failed + " failed) to " + out);
	}
}
