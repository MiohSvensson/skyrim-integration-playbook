import unittest

from synthesis_source_models import SourceModels, origin


class SourceModelTests(unittest.TestCase):
    def test_source_record_uses_original_object_id(self):
        source = {'sig': 'ARMA', 'fid': 0x02000874, 'edid': 'VA_CuirassAA',
                  'fields': [('MOD3', b'female.nif\0'), ('MOD5', b'first.nif\0')]}
        candidate = {'sig': 'ARMA', 'fid': 0x66000874, 'edid': 'VA_CuirassAA', 'fields': []}
        models = SourceModels(None, None, {'VindictorArmor.esp': ([], [source])})
        masters = [f'master{i}.esp' for i in range(102)] + ['VindictorArmor.esp']
        fields = models.fields_for(masters, candidate)
        self.assertEqual(origin(fields, 'MOD3', b'female.nif\0'), 'inherited_unchanged')
        self.assertEqual(origin(fields, 'MOD2', b'new-male.nif\0'), 'changed_by_synthesis')

    def test_source_editor_id_must_match(self):
        source = {'sig': 'ARMA', 'fid': 0x800, 'edid': 'different', 'fields': []}
        candidate = {'sig': 'ARMA', 'fid': 0x800, 'edid': 'expected', 'fields': []}
        models = SourceModels(None, None, {'mod.esp': ([], [source])})
        with self.assertRaises(ValueError):
            models.fields_for(['mod.esp'], candidate)

    def test_model_text_null_terminators_do_not_change_origin(self):
        self.assertEqual(origin({'MOD3': b'model.nif'}, 'MOD3', b'model.nif\0'), 'inherited_unchanged')

    def test_verified_input_context_wins_over_original_master(self):
        candidate = {'sig': 'ARMA', 'fid': 0x800, 'edid': 'expected', 'fields': []}
        source = {'sig': 'ARMA', 'fid': 0x800, 'edid': 'expected', 'fields': [('MOD3', b'original.nif\0')]}
        fields = {'mod.esp:000800': {'MOD3': b'pg-duplicate.nif\0'}}
        models = SourceModels(None, None, {'mod.esp': ([], [source])}, input_fields=fields)
        actual = models.fields_for(['mod.esp'], candidate)
        self.assertEqual(origin(actual, 'MOD3', b'pg-duplicate.nif\0'), 'inherited_unchanged')
        self.assertEqual(origin(actual, 'MOD3', b'original.nif\0'), 'changed_by_synthesis')
        with self.assertRaises(ValueError):
            models.fields_for(['mod.esp'], dict(candidate, fid=0x801))


if __name__ == '__main__':
    unittest.main()
