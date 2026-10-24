// List functions in an address range that Ghidra sees no references to (code or data).
// Args: <output file> <start> <end> <min size>
// @category TKToadstool
import java.io.FileWriter;
import java.io.PrintWriter;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.symbol.ReferenceIterator;

public class ListUnreferenced extends GhidraScript {
	@Override
	public void run() throws Exception {
		String[] a = getScriptArgs();
		Address start = toAddr(Long.decode(a[1]));
		Address end = toAddr(Long.decode(a[2]));
		long minSize = Long.decode(a[3]);
		try (PrintWriter out = new PrintWriter(new FileWriter(a[0]))) {
			FunctionIterator it = currentProgram.getFunctionManager().getFunctions(start, true);
			while (it.hasNext()) {
				Function f = it.next();
				Address e = f.getEntryPoint();
				if (e.compareTo(end) >= 0) {
					break;
				}
				long size = f.getBody().getMaxAddress().subtract(e) + 1;
				if (size < minSize || !f.getBody().getMinAddress().equals(e)) {
					continue;
				}
				ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(e);
				if (refs.hasNext()) {
					continue;
				}
				out.printf("%s\t%d\t%s%n", e, size, f.getName());
			}
		}
	}
}
