// Print disassembly around addresses, plus every instruction that references given data addresses.
// Args: <output file> <spec> [<spec> ...]
//   spec "0x8003e684:0x60"  dumps 0x60 bytes of instructions from that address
//   spec "ref:0x8026c7f8"   lists instructions whose operands or references hit that address
// @category TKToadstool
import java.io.FileWriter;
import java.io.PrintWriter;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;

public class DumpAsm extends GhidraScript {
	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
			for (int i = 1; i < args.length; i++) {
				if (args[i].startsWith("ref:")) {
					dumpRefs(out, Long.decode(args[i].substring(4)));
				}
				else {
					String[] parts = args[i].split(":");
					dumpRange(out, toAddr(Long.decode(parts[0])), Long.decode(parts[1]));
				}
			}
		}
	}

	private void dumpRange(PrintWriter out, Address start, long len) {
		Function f = getFunctionContaining(start);
		out.println("== " + start + " (" + (f == null ? "no function" : f.getName() + " @ " + f.getEntryPoint()) + ")");
		Address end = start.add(len);
		for (Address a = start; a.compareTo(end) < 0; a = a.add(4)) {
			Instruction ins = getInstructionAt(a);
			if (ins == null && getDataAt(a) == null) {
				disassemble(a);  // decode on demand (imports made with -noanalysis)
				ins = getInstructionAt(a);
			}
			String text = ins == null ? "(no instruction)" : ins.toString();
			out.printf("  %s  %08x  %s%n", a, readWord(a), text);
		}
	}

	private int readWord(Address a) {
		try {
			return currentProgram.getMemory().getInt(a);
		}
		catch (Exception e) {
			return 0;
		}
	}

	private void dumpRefs(PrintWriter out, long target) {
		out.printf("== instructions referencing 0x%08x%n", target);
		InstructionIterator it = currentProgram.getListing().getInstructions(true);
		long hi = (target + 0x8000) >>> 16;
		long lo = target & 0xffff;
		while (it.hasNext() && !monitor.isCancelled()) {
			Instruction ins = it.next();
			boolean hit = false;
			for (Reference r : ins.getReferencesFrom()) {
				if (r.getToAddress().getOffset() == target) {
					hit = true;
				}
			}
			if (!hit) {
				for (int op = 0; op < ins.getNumOperands(); op++) {
					for (Object o : ins.getOpObjects(op)) {
						if (o instanceof Scalar s && (s.getUnsignedValue() & 0xffff) == lo
								&& ins.getMnemonicString().matches("l[bhwf].*|st.*|addi")) {
							// Only report the low half when the matching high half is loaded nearby.
							for (int back = 1; back <= 6 && !hit; back++) {
								Instruction p = ins;
								for (int k = 0; k < back && p != null; k++) {
									p = p.getPrevious();
								}
								if (p != null && p.getMnemonicString().equals("lis")) {
									for (Object po : p.getOpObjects(1)) {
										if (po instanceof Scalar ps && (ps.getUnsignedValue() & 0xffff) == hi) {
											hit = true;
										}
									}
								}
							}
						}
					}
				}
			}
			if (hit) {
				Function f = getFunctionContaining(ins.getAddress());
				out.printf("  %s  %s   [%s]%n", ins.getAddress(), ins, f == null ? "?" : f.getName());
			}
		}
	}
}
