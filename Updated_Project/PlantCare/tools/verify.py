"""Run spec-derived tests and save machine-readable evidence; skips are not passes."""
import json,sys,unittest
from pathlib import Path
if __name__=='__main__':
    Path('evidence').mkdir(exist_ok=True)
    suite=unittest.defaultTestLoader.discover('tests')
    with Path('evidence/new_tests.txt').open('w') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    summary=dict(run=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),failure_tests=[str(t) for t,e in result.failures],error_tests=[str(t) for t,e in result.errors])
    Path('evidence/new_test_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2));sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)
