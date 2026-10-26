# Disassemble ranges / find data refs with Ghidra headless (DumpAsm.java) on an existing project.
# Usage: dumpasm.ps1 golf out.txt 0x804c6668:0x100 ref:0x804dae88 [-Root <folder holding tools\ and mod\ghidra_proj>]
# Projects (dol, golf, menu) come from ghidra_export.ps1; Root defaults to the folder above the repo.
param([Parameter(Mandatory, Position = 0)] [string] $Program, [Parameter(Mandatory, Position = 1)] [string] $Out,
	[Parameter(Position = 2, ValueFromRemainingArguments)] [string[]] $Specs,
	[string] $Root = (Join-Path $PSScriptRoot '..\..\..'))
$Root = (Resolve-Path $Root).Path  # Ghidra refuses project paths with '..' in them
$tools = Join-Path $Root 'tools'
$env:JAVA_HOME = Join-Path $tools 'jdk-21.0.12.1+1'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
$headless = Join-Path $tools 'ghidra_12.1.4_PUBLIC\support\analyzeHeadless.bat'
& $headless (Join-Path $Root 'mod\ghidra_proj') $Program -process -noanalysis -readOnly `
	-scriptPath (Resolve-Path (Join-Path $PSScriptRoot '..\ghidra_scripts')).Path `
	-postScript DumpAsm.java $Out @Specs *> "$Out.log"
Get-Content $Out
