import unittest

from synthesis_arma_diff import delta, source_key


class ArmaDeltaTests(unittest.TestCase):
    def test_master_insertion_does_not_change_source_identity(self):
        record = {'sig': 'ARMA', 'fid': 0x02000874, 'edid': 'VA_CuirassAA', 'fields': [('MOD2', b'Armor\\Aokili\\VA\\VA_Cuirass_m_1.nif\0')]}
        shifted = dict(record, fid=0x03000874)
        self.assertEqual(source_key(['Skyrim.esm', 'A.esp', 'VindictorArmor.esp'], record),
                         source_key(['Skyrim.esm', 'A.esp', 'Inserted.esm', 'VindictorArmor.esp'], shifted))

    def test_changed_and_new_records_are_affected(self):
        old = [{'sig': 'ARMA', 'fid': 0x00000800, 'fields': [('MOD2', b'old.nif\0')]},
               {'sig': 'ARMA', 'fid': 0x00000801, 'fields': [('MOD2', b'unchanged.nif\0')]}]
        new = [{'sig': 'ARMA', 'fid': 0x00000800, 'fields': [('MOD2', b'new.nif\0')]},
               {'sig': 'ARMA', 'fid': 0x00000801, 'fields': [('MOD2', b'unchanged.nif\0')]},
               {'sig': 'ARMA', 'fid': 0x00000802, 'fields': [('MOD2', b'added.nif\0')]}]
        result = delta(['Skyrim.esm'], old, ['Skyrim.esm', 'Inserted.esp'], new)
        self.assertEqual(result['affected_source_keys'], ['skyrim.esm:000800', 'skyrim.esm:000802'])
        self.assertEqual(len(result['model_changes']), 2)
        self.assertEqual(result['removed_source_records'], [])


if __name__ == '__main__':
    unittest.main()
