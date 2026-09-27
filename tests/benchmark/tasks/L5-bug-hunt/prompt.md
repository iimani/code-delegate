Bug report from finance:

> The daily sales report is wrong. When I run it for a single day, for example
> `python3 -m shop.cli.main --db shop.db report sales --from 2026-03-02 --to 2026-03-02`,
> it shows **0 orders** for a day on which we definitely took orders. For longer ranges the
> earlier days look right, but the **last day of the range is always empty**.

Find the root cause and fix it where it originates (not by working around it in the report). Orders placed at any time on the last day of a range, up to and including 23:59:59, must be counted, and nothing from the following day. Add a regression test that fails before your fix.

Python 3.9+, standard library only. The full suite must pass: `python3 -m unittest discover -s tests -t .`
