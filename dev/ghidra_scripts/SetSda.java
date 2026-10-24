// Seed the PowerPC EABI small-data base registers before auto-analysis.
// Args: <r2 value> <r13 value>, e.g. 0x802DF480 0x802DFA60
// @category TKToadstool
import java.math.BigInteger;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.ProgramContext;
import ghidra.program.model.mem.MemoryBlock;

public class SetSda extends GhidraScript {
	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		BigInteger r2 = BigInteger.valueOf(Long.decode(args[0]));
		BigInteger r13 = BigInteger.valueOf(Long.decode(args[1]));
		ProgramContext ctx = currentProgram.getProgramContext();
		for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
			if (!b.isExecute()) {
				continue;
			}
			ctx.setValue(ctx.getRegister("r2"), b.getStart(), b.getEnd(), r2);
			ctx.setValue(ctx.getRegister("r13"), b.getStart(), b.getEnd(), r13);
			println("Set r2/r13 over " + b.getName() + " " + b.getStart() + "-" + b.getEnd());
		}
	}
}
