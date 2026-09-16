# Examples

`sample_assignments.json` is fake data in the shape the connectors produce. To try the
scheduler and digest without a school login:

```bash
cp config.example.yaml config.yaml
mkdir -p data/kid1 data/kid2
python -c "
import json; items=json.load(open('examples/sample_assignments.json'))
for slug in ('kid1','kid2'):
    json.dump([a for a in items if a['student']==slug], open(f'data/{slug}/assignments.json','w'), indent=2)
"
school-planner --today 2026-09-16 schedule
school-planner --today 2026-09-16 digest
```
