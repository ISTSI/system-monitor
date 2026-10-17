"""Tests of v3 package oracles/assets only: no production API, DB or browser."""
from __future__ import annotations
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import stat
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from reference_contracts import load_json, validate_project
from reference_v2_contracts import policy_allows
from reference_v3_contracts import (scoped_key, event_identity, project_events, require_private_scope,
    validate_frame, validate_preview, check_limits, can_reserve, detach_workspace, reconcile_preview)
from inventory_fixture_reader import read_inventory, bundle_files, safe_data, InventoryError
try:
    import yaml
except ImportError:
    yaml = None


class ScopeContractTests(unittest.TestCase):
    def setUp(self):
        self.events = load_json('fixtures/multi-system/events.json')
        self.frame = load_json('contracts/live-frame.example.json')

    def test_two_projects_with_intentionally_repeated_local_ids(self):
        a=load_json('examples/systems/alpha.project.json'); b=load_json('examples/systems/beta.project.json')
        validate_project(a);validate_project(b)
        self.assertNotEqual(a['project']['id'],b['project']['id'])
        for key in ('servers','processes','connections','parsers','flows'):
            self.assertEqual(a[key],b[key])

    def test_catalog_preserves_two_distinct_system_ids(self):
        ids=[s['project_id'] for s in load_json('contracts/system-catalog.example.json')['items']]
        self.assertEqual(ids,['system-alpha','system-beta'])

    def test_event_identity_is_composite_without_rehashing_old_ids(self):
        self.assertEqual(len({e['event_id'] for e in self.events}),2)
        self.assertEqual(len({event_identity(e) for e in self.events}),4)

    def test_system_specific_query_cannot_include_other_system(self):
        for project,marker in [('system-alpha','ALPHA'),('system-beta','BETA')]:
            selected=project_events(self.events,project)
            self.assertEqual(len(selected),2)
            self.assertTrue(all('system_marker='+marker in e['raw_line'] for e in selected))

    def test_other_system_marker_returns_empty_not_foreign_results(self):
        self.assertEqual(project_events(self.events,'system-alpha','system_marker=BETA'),[])

    def test_scoped_cache_keys_differ_for_matching_local_ids(self):
        self.assertNotEqual(scoped_key('system-alpha','p-one','source-1'),scoped_key('system-beta','p-one','source-1'))
        self.assertNotEqual(scoped_key('a','b:c','d'),scoped_key('a','b','c:d'))

    def test_unsafe_namespace_identifiers_rejected(self):
        for value in ('../x','/tmp','bad/name','',None):
            with self.assertRaises(ValueError):scoped_key(value,'source')

    def test_private_scope_requires_both_project_and_owner(self):
        resource={'project_id':'a','owner_user_id':'u','workspace_id':'w'}
        require_private_scope(resource,project_id='a',actor_id='u',workspace_id='w')
        for kwargs in [dict(project_id='b',actor_id='u'),dict(project_id='a',actor_id='v')]:
            with self.assertRaisesRegex(ValueError,'NOT_FOUND'):require_private_scope(resource,**kwargs)

    def test_same_account_cannot_control_other_workspace_implicitly(self):
        with self.assertRaisesRegex(ValueError,'WORKSPACE_IN_USE'):
            require_private_scope({'project_id':'a','owner_user_id':'u','workspace_id':'w1'},project_id='a',actor_id='u',workspace_id='w2')

    def frame_args(self):
        return dict(project_id='system-alpha',workspace_id='workspace-alpha',session_id='live-alpha',filter_version=1)

    def test_valid_scoped_frame(self):validate_frame(self.frame,**self.frame_args())

    def test_old_project_workspace_session_filter_frames_rejected(self):
        for key,value in [('project_id','system-beta'),('workspace_id','workspace-beta'),('session_id','live-beta'),('filter_version',0)]:
            frame=deepcopy(self.frame);frame[key]=value
            with self.assertRaisesRegex(ValueError,'FRAME_SCOPE_MISMATCH'):validate_frame(frame,**self.frame_args())

    def test_event_must_agree_with_envelope(self):
        frame=deepcopy(self.frame);frame['payload']['items'][0]['project_id']='system-beta'
        with self.assertRaisesRegex(ValueError,'EVENT_SCOPE_MISMATCH'):validate_frame(frame,**self.frame_args())

    def test_legacy_protocol_fails_closed(self):
        frame=deepcopy(self.frame);frame['protocol_version']=1
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_PROTOCOL'):validate_frame(frame,**self.frame_args())

    def test_detach_one_window_preserves_other_window(self):
        sessions=[{'workspace_id':w,'owner_user_id':'u','state':'following'} for w in ['a','b']]
        result=detach_workspace(sessions,'a','u')
        self.assertEqual([s['state'] for s in result],['detached','following'])
        self.assertEqual([s['state'] for s in sessions],['following','following'])

    def test_detach_does_not_modify_another_user(self):
        sessions=[{'workspace_id':'a','owner_user_id':'v','state':'following'}]
        self.assertEqual(detach_workspace(sessions,'a','u'),sessions)

    def test_new_system_admin_actions_not_inspector_actions(self):
        for action in ['system.create','system.metadata.write','system.archive','system.restore','inventory.upload','inventory.source.manage','credential_binding.manage']:
            self.assertTrue(policy_allows('administrator',action,'u'))
            self.assertFalse(policy_allows('inspector',action,'u'))

    def test_workspace_creation_available_to_both_but_owner_is_server_assigned(self):
        for role in ['administrator','inspector']:
            self.assertTrue(policy_allows(role,'workspace.create','u'))
            self.assertFalse(policy_allows(role,'workspace.create','u',supplied_owner=True))

    def test_admin_inventory_upload_cancel_still_owner_checked(self):
        self.assertTrue(policy_allows('administrator','inventory.upload.cancel','u','u'))
        self.assertFalse(policy_allows('administrator','inventory.upload.cancel','u','v'))
        self.assertFalse(policy_allows('inspector','inventory.upload.cancel','u','u'))


class PreviewAndBudgetTests(unittest.TestCase):
    def setUp(self):
        self.binding=load_json('contracts/inventory-preview-binding.example.json')
        self.limits=load_json('examples/deployment-policy.example.json')['limits']

    def preview_args(self):
        b=self.binding
        return dict(project_id=b['project_id'],actor_id=b['owner_user_id'],auth_version=b['auth_version'],source_id=b['inventory_source_id'],revision=b['expected_revision'],content_sha256=b['content_sha256'],mapping_sha256=b['mapping_sha256'],now_utc='2026-10-17T10:00:00.000000Z')

    def test_valid_preview_binding(self):validate_preview(self.binding,**self.preview_args())

    def test_preview_rejects_other_system_or_owner(self):
        for key in ['project_id','actor_id']:
            args=self.preview_args();args[key]='other'
            with self.assertRaisesRegex(ValueError,'NOT_FOUND'):validate_preview(self.binding,**args)

    def test_preview_rejects_all_changed_binding_fields(self):
        for key,val in [('auth_version',2),('source_id','other'),('revision',2),('content_sha256','a'*64),('mapping_sha256','b'*64)]:
            args=self.preview_args();args[key]=val
            with self.assertRaisesRegex(ValueError,'PREVIEW_CONFLICT'):validate_preview(self.binding,**args)

    def test_preview_expiry_is_exclusive(self):
        args=self.preview_args();args['now_utc']=self.binding['expires_at']
        with self.assertRaisesRegex(ValueError,'PREVIEW_EXPIRED'):validate_preview(self.binding,**args)

    def test_default_limits_allow_two_windows_five_processes_each(self):
        check_limits(load_json('examples/deployment-policy.example.json'))
        existing=[]
        for project,workspace in [('a','wa'),('b','wb')]:
            request=dict(owner_user_id='u',project_id=project,workspace_id=workspace,process_count=5)
            self.assertTrue(can_reserve(existing,request,self.limits));existing.append(request)
        self.assertEqual(sum(r['process_count'] for r in existing),10)

    def test_eleventh_source_rejected_without_mutating_existing_reservations(self):
        existing=[dict(owner_user_id='u',project_id=p,workspace_id='w'+p,process_count=5) for p in ['a','b']]
        original=deepcopy(existing)
        self.assertFalse(can_reserve(existing,dict(owner_user_id='u',project_id='c',workspace_id='wc',process_count=1),self.limits))
        self.assertEqual(original,existing)

    def test_workspace_limit_not_bypassed_by_large_global_budget(self):
        self.assertFalse(can_reserve([],dict(owner_user_id='u',project_id='a',workspace_id='wa',process_count=6),self.limits))

    def test_bad_limits_rejected(self):
        for key,val in [('max_live_processes_per_workspace',11),('max_live_processes_per_project',11),('max_workspaces_per_user',65),('max_live_processes_per_workspace',True)]:
            cfg=load_json('examples/deployment-policy.example.json');cfg['limits'][key]=val
            with self.assertRaises(ValueError):check_limits(cfg)

    def test_optional_defaults_fit_lower_explicit_legacy_caps(self):
        cfg=load_json('examples/deployment-policy.example.json')
        for key in ['max_live_processes_per_project','max_live_processes_per_workspace',
                    'max_collection_jobs_per_project','max_workspaces_per_user','max_workspaces_global']:
            cfg['limits'].pop(key,None)
        cfg['limits']['max_live_processes_per_user']=2
        cfg['limits']['max_live_processes_global']=2
        cfg['limits']['max_collection_jobs_global']=1
        cfg['limits']['max_collection_jobs_per_user']=1
        before=deepcopy(cfg)
        check_limits(cfg)
        self.assertEqual(cfg,before)  # No silent mutation/raising of custom caps.

    def rows(self):
        return [dict(project_id=p,inventory_source_id='inventory-main',inventory_hostname='same-host',server_id='h-one',host='192.0.2.1',description='Manual note '+p,layout={'x':11,'y':23}) for p in ['a','b']]

    def test_idempotent_reimport_only_matches_selected_project(self):
        report=reconcile_preview(self.rows(),[dict(inventory_hostname='same-host',host='192.0.2.1')],project_id='a',source_id='inventory-main')
        self.assertEqual(len(report['unchanged']),1);self.assertEqual(report['unchanged'][0]['project_id'],'a')
        self.assertEqual(report['changed'],[]);self.assertEqual(report['added'],[])

    def test_changed_host_preserves_ids_notes_layout_and_other_project(self):
        rows=self.rows();original=deepcopy(rows)
        report=reconcile_preview(rows,[dict(inventory_hostname='same-host',host='192.0.2.2')],project_id='a',source_id='inventory-main')
        self.assertEqual(report['changed'],[dict(existing_id='h-one',old_host='192.0.2.1',new_host='192.0.2.2',preserved_documentation='Manual note a',preserved_layout={'x':11,'y':23})])
        self.assertEqual(rows,original)

    def test_missing_hosts_preserved_not_deleted(self):
        report=reconcile_preview(self.rows(),[],project_id='a',source_id='inventory-main')
        self.assertEqual(len(report['absent_preserved']),1);self.assertNotIn('deleted',report)

    def test_same_filename_new_source_does_not_merge_by_ip(self):
        report=reconcile_preview(self.rows(),[dict(inventory_hostname='same-host',host='192.0.2.1')],project_id='a',source_id='other-source')
        self.assertEqual(len(report['added']),1);self.assertEqual(report['unchanged'],[])

    def test_duplicate_aliases_rejected(self):
        row=dict(inventory_hostname='same-host',host='192.0.2.1')
        with self.assertRaises(ValueError):reconcile_preview([], [row,row],project_id='a',source_id='s')


@unittest.skipIf(yaml is None,'PyYAML is required for package inventory example checks; no network installation')
class InventoryExampleTests(unittest.TestCase):
    def data(self,name):return (ROOT/'examples/ansible'/name).read_bytes()
    def basic_hosts(self,result):
        return [(h['inventory_hostname'],h['host'],h['port'],h['username']) for h in result['hosts']]
    def expected_hosts(self):
        return [('demo-core-01','192.0.2.21',22,'logreader'),('demo-delivery-01','192.0.2.22',22,'logreader'),('demo-ingest-01','192.0.2.20',22,'logreader')]

    def test_ini_and_extensionless_files_directly(self):
        for name in ['hosts','inventory.hosts.ini']:
            result=read_inventory(self.data(name),'ini')
            self.assertEqual(self.basic_hosts(result),self.expected_hosts())
            self.assertEqual(sum(len(h['inspector_processes']) for h in result['hosts']),0)

    def test_static_yaml_with_process_definitions(self):
        result=read_inventory(self.data('inventory.static.yaml'),'yaml')
        self.assertEqual(self.basic_hosts(result),self.expected_hosts())
        self.assertEqual([len(h['inspector_processes']) for h in result['hosts']],[2,2,1])

    def test_canonical_json_with_process_definitions(self):
        result=read_inventory(self.data('inventory.canonical.json'),'canonical_json')
        self.assertEqual(self.basic_hosts(result),self.expected_hosts())
        self.assertEqual([len(h['inspector_processes']) for h in result['hosts']],[2,2,1])

    def test_bundle_relative_group_and_host_vars(self):
        files=bundle_files(self.data('inventory-with-vars.zip'))
        main=files.pop('hosts.ini');result=read_inventory(main,'ini',files)
        self.assertEqual(self.basic_hosts(result),self.expected_hosts())
        self.assertEqual([len(h['inspector_processes']) for h in result['hosts']],[2,2,1])
        self.assertEqual([h['inspector_subsystem'] for h in result['hosts']],['s-core','s-delivery','s-ingress'])

    def test_bundle_matches_source_tree_exactly(self):
        files=bundle_files(self.data('inventory-with-vars.zip'))
        expected={p.relative_to(ROOT/'examples/ansible/bundle').as_posix():p.read_bytes() for p in (ROOT/'examples/ansible/bundle').rglob('*') if p.is_file()}
        self.assertEqual(files,expected)

    def test_missing_companions_do_not_invent_processes(self):
        result=read_inventory(self.data('bundle/hosts.ini'),'ini')
        self.assertTrue(all(h['inspector_processes']==[] and h['username'] is None for h in result['hosts']))

    def test_nested_group_inheritance(self):
        result=read_inventory(b'all:\n  vars:\n    ansible_user: parent\n  children:\n    app:\n      vars:\n        ansible_user: child\n      hosts:\n        node: {}\n','yaml')
        self.assertEqual(result['hosts'][0]['username'],'child')

    def test_quoted_ini_username_with_group_vars(self):
        result=read_inventory(b'[app]\nnode ansible_host=192.0.2.4\n[app:vars]\nansible_user="log reader"\n','ini')
        self.assertEqual(result['hosts'][0]['username'],'log reader')

    def test_secret_fields_omitted_without_values(self):
        raw=b'all:\n  hosts:\n    node:\n      ansible_user: logreader\n      ansible_password: synthetic-secret-value\n      ansible_ssh_common_args: synthetic-unsafe-command\n'
        result=read_inventory(raw,'yaml');serialized=json.dumps(result)
        self.assertNotIn('synthetic-secret-value',serialized);self.assertNotIn('synthetic-unsafe-command',serialized)
        self.assertIn('ansible_password',result['omitted_fields'])

    def test_dynamic_template_vault_and_nonssh_inputs_rejected(self):
        cases=[b'plugin: amazon.aws.aws_ec2\n',b'all:\n  hosts:\n    node:\n      ansible_host: "{{ lookup(\'env\',\'HOST\') }}"\n',b'$ANSIBLE_VAULT;1.1;AES256\nabcdef',b'all:\n  hosts:\n    node:\n      ansible_connection: local\n']
        for raw in cases:
            with self.assertRaises(InventoryError):read_inventory(raw,'yaml')

    def test_duplicate_yaml_json_and_unsafe_tags_rejected(self):
        for raw,fmt in [(b'all: {}\nall: {}\n','yaml'),(b'all: &x {}\ncopy: *x\n','yaml'),(b'!!python/object:Thing {}\n','yaml'),(b'{"all":{},"all":{}}','canonical_json')]:
            with self.assertRaises(InventoryError):read_inventory(raw,fmt)

    def test_group_cycles_and_sibling_conflicts_rejected(self):
        cycle=b'[a:children]\nb\n[b:children]\na\n'
        conflict=b'[a]\nnode\n[a:vars]\nansible_user=one\n[b]\nnode\n[b:vars]\nansible_user=two\n'
        for raw in [cycle,conflict]:
            with self.assertRaises(InventoryError):read_inventory(raw,'ini')

    def test_host_range_rejected_not_used_as_literal_target(self):
        with self.assertRaises(InventoryError):read_inventory(b'[all]\nnode[01:99]\n','ini')

    def make_zip(self,files):
        stream=BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            for name,data,mode in files:
                entry=zipfile.ZipInfo(name)
                # Preserve malformed names exactly: ZipInfo's constructor
                # normalizes backslashes on Windows and truncates NULs.
                entry.filename=name;entry.orig_filename=name
                entry.external_attr=mode<<16;z.writestr(entry,data)
        return stream.getvalue()

    def test_unsafe_zip_paths_links_nested_archives_rejected(self):
        for name,mode in [('../hosts',0o100644),('/hosts',0o100644),('C:/hosts',0o100644),('x\\hosts',0o100644),('hosts',stat.S_IFLNK|0o777),('inner.zip',0o100644)]:
            with self.subTest(name=name,mode=mode):
                with self.assertRaises(InventoryError):bundle_files(self.make_zip([(name,b'not executed',mode)]))

    def test_raw_zip_names_rejected_before_platform_normalization(self):
        for name in ['x\\hosts','hosts\x00ignored']:
            with self.subTest(name=name):
                raw=self.make_zip([(name,b'not executed',0o100644)])
                with zipfile.ZipFile(BytesIO(raw)) as archive:
                    self.assertEqual(archive.infolist()[0].orig_filename,name)
                with self.assertRaisesRegex(InventoryError,'UNSAFE_MEMBER'):
                    bundle_files(raw)

    def test_zip_case_collision_rejected(self):
        with self.assertRaisesRegex(InventoryError,'DUPLICATE_MEMBER'):
            bundle_files(self.make_zip([('hosts',b'a',0o100644),('HOSTS',b'b',0o100644)]))

    def test_parser_error_does_not_echo_sensitive_value(self):
        secret='sentinel-do-not-echo'
        try:read_inventory(f'all:\n  hosts: [broken:{secret}\n'.encode(),'yaml')
        except InventoryError as exc:self.assertNotIn(secret,str(exc))
        else:self.fail('Invalid YAML accepted')


if __name__=='__main__':unittest.main()
