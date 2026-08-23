# Baseline and Change Control

## Baseline

v1.0.24.23 is the current candidate stable desktop baseline because the user reported that it finally feels stable and the visible feature set appears to work. Production behavior is still subject to real-use verification.

## Golden rule

A new version starts from this exact source tree unless a documented recovery procedure proves otherwise.

Never choose an older version as a wholesale replacement simply because it was once called stable.

## Regression rule

Before releasing a change:
1. preserve the baseline ZIP and hash;
2. make the smallest scoped change;
3. run syntax validation;
4. run pre-build validation;
5. run accumulated functionality validation;
6. run public identity scan;
7. build;
8. smoke-start;
9. exercise the changed workflow;
10. verify previously approved workflows remain present.

## Historical-function rule

If a previously approved function disappears and there is no later explicit decision removing/replacing it, treat the disappearance as a regression.

## Version documentation

Every release should include:
- exact parent version;
- changed files;
- behavior changed;
- behavior explicitly not changed;
- DB schema change: yes/no;
- migration required: yes/no;
- tests actually performed;
- tests not performed;
- SHA-256.
