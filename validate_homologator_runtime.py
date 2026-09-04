from pathlib import Path
import shutil, sqlite3, tempfile
from codecafe_atlas.database import Database
from codecafe_atlas.sync_engine import SyncEngine


def syncrow(path, eid):
    with sqlite3.connect(path) as c:
        c.row_factory=sqlite3.Row
        return c.execute("SELECT * FROM atlas_sync_records WHERE entity_type='buildings' AND entity_id=?",(eid,)).fetchone()

def set_identity(path,eid,uid,rev,created,updated):
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO atlas_sync_records(entity_type,entity_id,record_uuid,revision,created_by_installation,updated_by_installation) VALUES('buildings',?,?,?,?,?) ON CONFLICT(entity_type,entity_id) DO UPDATE SET record_uuid=excluded.record_uuid,revision=excluded.revision,created_by_installation=excluded.created_by_installation,updated_by_installation=excluded.updated_by_installation",(eid,uid,rev,created,updated))

def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); lp=root/'local'/'data'/'atlas.db'; ep=root/'external'/'data'/'atlas.db'
        ldb=Database(lp); edb=Database(ep)
        vals={'name':'Edificio Central','city':'Torreón','state':'Coahuila','country':'México'}
        lid=ldb.save_building(vals); eid=edb.save_building({**vals,'city':'Gómez Palacio'})
        set_identity(lp,lid,'local-uuid',1,'LOCAL','LOCAL')
        set_identity(ep,eid,'external-uuid',7,'EXT','EXT')
        eng=SyncEngine(lp,ep); plan=eng.analyze()
        item=next(x for x in plan.items if x.table=='buildings' and x.status=='Posible duplicado')
        item.decision='Usar externo'; eng.apply(plan,root/'reports')
        r=syncrow(lp,lid)
        assert r['record_uuid']=='external-uuid', dict(r)
        assert r['revision']==7, dict(r)
        assert r['created_by_installation']=='EXT' and r['updated_by_installation']=='EXT', dict(r)
        plan2=SyncEngine(lp,ep).analyze()
        item2=next(x for x in plan2.items if x.table=='buildings' and x.external_id is not None)
        assert item2.status=='Coincidente', item2
        plan2.close()

        # Same UUID conflict must carry revision/provenance when external is selected.
        with sqlite3.connect(ep) as c:
            c.execute("UPDATE atlas_buildings SET city='Lerdo' WHERE id=?",(eid,))
            c.execute("UPDATE atlas_sync_records SET revision=9,updated_by_installation='EXT2' WHERE entity_type='buildings' AND entity_id=?",(eid,))
        plan3=SyncEngine(lp,ep).analyze(); i3=next(x for x in plan3.items if x.table=='buildings' and x.external_id is not None)
        assert i3.status=='Conflicto'; i3.decision='Usar externo'; SyncEngine(lp,ep).apply(plan3,root/'reports')
        r=syncrow(lp,lid); assert r['revision']==9 and r['updated_by_installation']=='EXT2', dict(r)

        # Stale plan must be rejected and local DB restored unchanged.
        plan4=SyncEngine(lp,ep).analyze()
        with sqlite3.connect(ep) as c: c.execute("UPDATE atlas_buildings SET city='Durango' WHERE id=?",(eid,))
        try:
            SyncEngine(lp,ep).apply(plan4,root/'reports')
        except ValueError as exc:
            assert 'cambió desde el análisis' in str(exc)
        else:
            raise AssertionError('A stale homologation plan was accepted')
    print('HOMOLOGATOR RUNTIME VALIDATION: PASS')

if __name__=='__main__': main()
