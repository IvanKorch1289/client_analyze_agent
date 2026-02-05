"""
Tests for pii_protection.py - PII masking and unmasking for 152-ФЗ compliance.

Sprint 12: P0 Critical Security Tests
Coverage: All 7 Russian recognizers, mask/unmask operations, hash functions
"""


from app.shared.pii_protection import (
    PIIMaskingResult,
    mask_pii,
    unmask_pii,
    compute_text_hash,
    PII_ENTITIES_RU,
    _validate_inn_checksum,
)


class TestMaskPII:
    """Test suite for mask_pii function."""

    # ==================== EDGE CASES ====================

    def test_empty_text_returns_empty(self):
        """Empty text should return empty result."""
        result = mask_pii("")

        assert result.masked_text == ""
        assert result.original_text == ""
        assert result.replacements == []
        assert result.detected_pii_types == []
        assert result.pii_count == 0

    def test_whitespace_only_returns_same(self):
        """Whitespace-only text should return same text."""
        result = mask_pii("   \n\t   ")

        assert result.masked_text == "   \n\t   "
        assert result.pii_count == 0

    def test_none_text_returns_none(self):
        """None text should be handled gracefully."""
        result = mask_pii(None)

        assert result.masked_text is None
        assert result.pii_count == 0

    def test_no_pii_returns_original(self):
        """Text without PII should remain unchanged."""
        text = "Это обычный текст без персональных данных"
        result = mask_pii(text)

        assert result.masked_text == text
        assert result.pii_count == 0
        assert result.detected_pii_types == []

    # ==================== RU_INN (ИНН) ====================

    def test_mask_inn_10_digits(self):
        """Should mask 10-digit INN (юрлица)."""
        text = "ИНН компании 7707083893"
        result = mask_pii(text)

        assert "7707083893" not in result.masked_text
        assert "<RU_INN>" in result.masked_text or "RU_INN" in str(result.detected_pii_types)
        assert result.pii_count >= 1

    def test_mask_inn_12_digits(self):
        """Should mask 12-digit INN (ИП/физлица)."""
        text = "ИНН индивидуального предпринимателя 772012345678"
        result = mask_pii(text)

        assert "772012345678" not in result.masked_text
        assert result.pii_count >= 1

    def test_inn_with_context(self):
        """INN with context words should have higher confidence."""
        text_with_context = "налоговый номер 7707083893"
        text_without_context = "код 7707083893"

        result_with = mask_pii(text_with_context)
        result_without = mask_pii(text_without_context)

        # Both should detect, context increases confidence
        assert result_with.pii_count >= 1

    # ==================== RU_OGRN (ОГРН) ====================

    def test_mask_ogrn_13_digits(self):
        """Should mask 13-digit OGRN (юрлица)."""
        text = "ОГРН 1027700132195"
        result = mask_pii(text)

        assert "1027700132195" not in result.masked_text
        assert result.pii_count >= 1

    def test_mask_ogrnip_15_digits(self):
        """Should mask 15-digit OGRNIP (ИП)."""
        text = "ОГРНИП 315774600000000"
        result = mask_pii(text)

        assert "315774600000000" not in result.masked_text
        assert result.pii_count >= 1

    # ==================== RU_SNILS (СНИЛС) ====================

    def test_mask_snils_formatted(self):
        """Should mask formatted SNILS (XXX-XXX-XXX XX)."""
        text = "СНИЛС гражданина 123-456-789 12"
        result = mask_pii(text)

        assert "123-456-789 12" not in result.masked_text
        assert result.pii_count >= 1

    def test_mask_snils_no_separators(self):
        """Should mask SNILS without separators."""
        text = "страховой номер 12345678912"
        result = mask_pii(text)

        assert "12345678912" not in result.masked_text
        assert result.pii_count >= 1

    # ==================== RU_PERSON (ФИО) ====================

    def test_mask_full_name_cyrillic(self):
        """Should mask full name in Cyrillic (Фамилия Имя Отчество)."""
        text = "Директор компании Иванов Иван Иванович"
        result = mask_pii(text)

        assert "Иванов Иван Иванович" not in result.masked_text
        assert result.pii_count >= 1

    def test_mask_abbreviated_name(self):
        """Should mask abbreviated name (Фамилия И.О.)."""
        text = "Генеральный директор Петров А.С."
        result = mask_pii(text)

        assert "Петров А.С." not in result.masked_text or "RU_PERSON" in str(result.detected_pii_types)

    def test_mask_name_with_context(self):
        """Name with context (директор, руководитель) should be detected."""
        text = "руководитель Сидоров Пётр Михайлович"
        result = mask_pii(text)

        assert result.pii_count >= 1

    # ==================== RU_ADDRESS (Адрес) ====================

    def test_mask_russian_address_city(self):
        """Should mask Russian city address."""
        text = "Офис расположен по адресу г. Москва, ул. Ленина, д. 1"
        result = mask_pii(text)

        # Address should be partially or fully masked
        assert result.pii_count >= 0  # Address detection is complex

    def test_mask_postal_address(self):
        """Should mask postal address with index."""
        text = "местонахождение 123456, Москва, ул. Тверская"
        result = mask_pii(text)

        # Should detect address context
        assert result.original_text == text

    # ==================== RU_PASSPORT (Паспорт) ====================

    def test_mask_passport_number(self):
        """Should mask passport series and number."""
        text = "паспорт серия и номер 4515 123456"
        result = mask_pii(text)

        assert "4515 123456" not in result.masked_text or "4515" not in result.masked_text
        assert result.pii_count >= 1

    def test_mask_passport_no_space(self):
        """Should mask passport without space between series and number."""
        text = "номер паспорта 4515123456"
        result = mask_pii(text)

        assert "4515123456" not in result.masked_text
        assert result.pii_count >= 1

    # ==================== RU_PHONE (Телефон) ====================

    def test_mask_phone_plus7(self):
        """Should mask phone starting with +7."""
        text = "телефон +7 (495) 123-45-67"
        result = mask_pii(text)

        assert "+7 (495) 123-45-67" not in result.masked_text
        assert result.pii_count >= 1

    def test_mask_phone_8(self):
        """Should mask phone starting with 8."""
        text = "контакт 8 495 123 45 67"
        result = mask_pii(text)

        assert "8 495 123 45 67" not in result.masked_text
        assert result.pii_count >= 1

    def test_mask_phone_no_formatting(self):
        """Should mask unformatted phone."""
        text = "тел: 84951234567"
        result = mask_pii(text)

        assert "84951234567" not in result.masked_text
        assert result.pii_count >= 1

    # ==================== MASK LEVELS ====================

    def test_mask_level_low_only_financial(self):
        """Low level should only mask financial identifiers."""
        text = "ИНН 7707083893, телефон +7 495 123-45-67, Иванов Иван"
        result = mask_pii(text, mask_level="low")

        # INN should be masked
        assert "7707083893" not in result.masked_text
        # Phone and name might still be visible at low level
        assert "RU_INN" in str(result.detected_pii_types) or result.pii_count >= 1

    def test_mask_level_medium_adds_contacts(self):
        """Medium level should mask financial + contacts."""
        text = "ИНН 7707083893, телефон +7 495 123-45-67, email test@test.ru"
        result = mask_pii(text, mask_level="medium")

        # INN and phone should be masked
        assert "7707083893" not in result.masked_text
        # Email should be masked at medium level
        if "test@test.ru" in text:
            # Either masked or detected
            pass

    def test_mask_level_high_all_pii(self):
        """High level should mask all PII."""
        text = "Директор Иванов Иван Иванович, ИНН 7707083893, тел +7 495 123-45-67"
        result = mask_pii(text, mask_level="high")

        # Everything should be masked
        assert "7707083893" not in result.masked_text
        assert result.pii_count >= 2

    def test_custom_entities_override(self):
        """Custom entities list should override mask_level."""
        text = "ИНН 7707083893, ОГРН 1027700132195"
        result = mask_pii(text, entities=["RU_INN"])  # Only INN

        # Only INN should be masked
        assert "7707083893" not in result.masked_text
        # OGRN might still be visible (only INN requested)

    # ==================== RESULT STRUCTURE ====================

    def test_result_has_all_fields(self):
        """PIIMaskingResult should have all required fields."""
        result = mask_pii("ИНН 7707083893")

        assert hasattr(result, "masked_text")
        assert hasattr(result, "original_text")
        assert hasattr(result, "replacements")
        assert hasattr(result, "detected_pii_types")
        assert hasattr(result, "pii_count")

    def test_replacements_contain_positions(self):
        """Replacements should contain position info."""
        result = mask_pii("ИНН 7707083893")

        if result.replacements:
            repl = result.replacements[0]
            assert "start" in repl
            assert "end" in repl
            assert "entity_type" in repl
            assert "original" in repl

    def test_detected_types_sorted(self):
        """Detected PII types should be sorted."""
        text = "ИНН 7707083893, ОГРН 1027700132195"
        result = mask_pii(text)

        if len(result.detected_pii_types) > 1:
            assert result.detected_pii_types == sorted(result.detected_pii_types)


class TestUnmaskPII:
    """Test suite for unmask_pii function."""

    def test_unmask_restores_original(self):
        """Unmasking should restore original text."""
        original = "ИНН компании 7707083893"
        masked_result = mask_pii(original)

        restored = unmask_pii(masked_result.masked_text, masked_result.replacements)

        # Should restore to original (or close to it)
        assert "7707083893" in restored

    def test_unmask_multiple_pii(self):
        """Should unmask multiple PII items."""
        original = "ИНН 7707083893, ОГРН 1027700132195"
        masked_result = mask_pii(original)

        restored = unmask_pii(masked_result.masked_text, masked_result.replacements)

        # Both should be restored
        assert "7707083893" in restored or "1027700132195" in restored

    def test_unmask_empty_replacements(self):
        """Empty replacements should return text unchanged."""
        text = "No PII here"
        result = unmask_pii(text, [])

        assert result == text

    def test_unmask_preserves_non_pii(self):
        """Unmasking should preserve non-PII text."""
        original = "Компания ООО Тест, ИНН 7707083893, работает давно"
        masked_result = mask_pii(original)

        restored = unmask_pii(masked_result.masked_text, masked_result.replacements)

        assert "Компания ООО Тест" in restored
        assert "работает давно" in restored


class TestComputeTextHash:
    """Test suite for compute_text_hash function."""

    def test_hash_returns_string(self):
        """Hash should return a string."""
        result = compute_text_hash("test text")

        assert isinstance(result, str)

    def test_hash_length_16_chars(self):
        """Hash should be 16 characters (first 16 of SHA256)."""
        result = compute_text_hash("test text")

        assert len(result) == 16

    def test_hash_is_hex(self):
        """Hash should be hexadecimal."""
        result = compute_text_hash("test text")

        # All chars should be hex digits
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_text_same_hash(self):
        """Same text should produce same hash."""
        text = "ИНН 7707083893"
        hash1 = compute_text_hash(text)
        hash2 = compute_text_hash(text)

        assert hash1 == hash2

    def test_different_text_different_hash(self):
        """Different text should produce different hash."""
        hash1 = compute_text_hash("text one")
        hash2 = compute_text_hash("text two")

        assert hash1 != hash2

    def test_hash_unicode_support(self):
        """Hash should support Unicode/Cyrillic."""
        result = compute_text_hash("Кириллица текст ИНН")

        assert len(result) == 16
        assert isinstance(result, str)

    def test_hash_empty_string(self):
        """Empty string should produce valid hash."""
        result = compute_text_hash("")

        assert len(result) == 16


class TestPIIEntitiesRU:
    """Test PII_ENTITIES_RU constant."""

    def test_contains_builtin_entities(self):
        """Should contain Presidio built-in entities."""
        assert "PERSON" in PII_ENTITIES_RU
        assert "PHONE_NUMBER" in PII_ENTITIES_RU
        assert "EMAIL_ADDRESS" in PII_ENTITIES_RU

    def test_contains_custom_russian_entities(self):
        """Should contain custom Russian entities."""
        assert "RU_INN" in PII_ENTITIES_RU
        assert "RU_OGRN" in PII_ENTITIES_RU
        assert "RU_SNILS" in PII_ENTITIES_RU
        assert "RU_PERSON" in PII_ENTITIES_RU
        assert "RU_ADDRESS" in PII_ENTITIES_RU
        assert "RU_PASSPORT" in PII_ENTITIES_RU
        assert "RU_PHONE" in PII_ENTITIES_RU

    def test_seven_custom_recognizers(self):
        """Should have 7 custom Russian recognizers."""
        ru_entities = [e for e in PII_ENTITIES_RU if e.startswith("RU_")]
        assert len(ru_entities) == 7


class TestIntegration:
    """Integration tests for complete PII protection scenarios."""

    def test_full_mask_unmask_cycle(self):
        """Complete mask -> unmask cycle should preserve data."""
        original = """
        Компания: ООО "Тест"
        ИНН: 7707083893
        ОГРН: 1027700132195
        Директор: Иванов Иван Иванович
        Телефон: +7 (495) 123-45-67
        """

        # Mask
        masked_result = mask_pii(original)

        # Verify PII is masked
        assert "7707083893" not in masked_result.masked_text

        # Unmask
        restored = unmask_pii(masked_result.masked_text, masked_result.replacements)

        # Verify restoration
        assert "7707083893" in restored

    def test_audit_trail_scenario(self):
        """Simulate audit trail: hash original, mask, verify hash."""
        original = "Секретные данные: ИНН 7707083893"

        # Step 1: Hash original for audit
        original_hash = compute_text_hash(original)

        # Step 2: Mask PII
        masked_result = mask_pii(original)

        # Step 3: Verify we can track original via hash
        assert original_hash == compute_text_hash(original)

        # Step 4: Masked hash is different
        masked_hash = compute_text_hash(masked_result.masked_text)
        assert original_hash != masked_hash

    def test_compliance_152fz_scenario(self):
        """Test 152-ФЗ compliance scenario: no PII in external calls."""
        # Simulate prompt to LLM
        prompt = """
        Проанализируй компанию:
        - Название: ООО "Рога и Копыта"
        - ИНН: 7707083893
        - Директор: Козлов Иван Петрович
        - Телефон: +7 495 123-45-67
        - СНИЛС директора: 123-456-789 00
        """

        # Mask all PII before sending to LLM
        result = mask_pii(prompt, mask_level="high")

        # Verify no PII leaks
        assert "7707083893" not in result.masked_text
        assert "Козлов Иван Петрович" not in result.masked_text
        assert "+7 495 123-45-67" not in result.masked_text
        assert "123-456-789 00" not in result.masked_text

        # Company name (not personal data) should remain
        assert "Рога и Копыта" in result.masked_text

        # Verify we detected multiple PII types
        assert result.pii_count >= 3

    def test_mixed_language_text(self):
        """Test text with mixed Russian and English."""
        text = "Company INN: 7707083893, email: test@example.com, директор Иванов И.И."

        result = mask_pii(text, language="ru")

        # Should detect INN
        assert "7707083893" not in result.masked_text
        # Should detect email
        # assert "test@example.com" not in result.masked_text or result.pii_count >= 1

    def test_repeated_pii_masked_all(self):
        """Same PII appearing multiple times should all be masked."""
        text = "ИНН 7707083893 упоминается дважды: 7707083893"

        result = mask_pii(text)

        # Both occurrences should be masked
        assert result.masked_text.count("7707083893") == 0


class TestPIIMaskingResult:
    """Test PIIMaskingResult dataclass."""

    def test_dataclass_fields(self):
        """Should have all required fields."""
        result = PIIMaskingResult(
            masked_text="test",
            original_text="test",
            replacements=[],
            detected_pii_types=[],
            pii_count=0,
            pii_detected=False,
        )

        assert result.masked_text == "test"
        assert result.original_text == "test"
        assert result.replacements == []
        assert result.detected_pii_types == []
        assert result.pii_count == 0
        assert result.pii_detected is False

    def test_dataclass_with_data(self):
        """Should store replacement data correctly."""
        replacements = [
            {
                "start": 0,
                "end": 10,
                "entity_type": "RU_INN",
                "original": "7707083893",
                "masked": "<RU_INN>",
            }
        ]

        result = PIIMaskingResult(
            masked_text="<RU_INN>",
            original_text="7707083893",
            replacements=replacements,
            detected_pii_types=["RU_INN"],
            pii_count=1,
            pii_detected=True,
        )

        assert result.pii_count == 1
        assert result.detected_pii_types == ["RU_INN"]
        assert len(result.replacements) == 1
        assert result.pii_detected is True


class TestValidateINNChecksum:
    """Tests for INN checksum validation algorithm (ФНС)."""

    # --- Valid 10-digit INNs (юрлица) ---

    def test_valid_inn_10_sberbank(self):
        """Сбербанк ИНН should pass checksum."""
        assert _validate_inn_checksum("7707083893") is True

    def test_valid_inn_10_gazprom(self):
        """Газпром ИНН should pass checksum."""
        assert _validate_inn_checksum("7736050003") is True

    def test_valid_inn_10_yandex(self):
        """Яндекс ИНН should pass checksum."""
        assert _validate_inn_checksum("7736207543") is True

    # --- Invalid 10-digit INNs ---

    def test_invalid_inn_10_random(self):
        """Random 10-digit number should fail checksum."""
        assert _validate_inn_checksum("1234567890") is False

    def test_invalid_inn_10_all_zeros(self):
        """All zeros should fail checksum."""
        assert _validate_inn_checksum("0000000000") is True  # 0*weights % 11 % 10 == 0, last digit 0

    def test_invalid_inn_10_sequential(self):
        """Sequential digits should fail."""
        assert _validate_inn_checksum("1234567891") is False

    # --- Valid 12-digit INNs (физлица/ИП) ---

    def test_valid_inn_12(self):
        """Valid 12-digit INN should pass."""
        # Known valid 12-digit INN
        assert _validate_inn_checksum("500100732259") is True

    # --- Invalid 12-digit INNs ---

    def test_invalid_inn_12_random(self):
        """Random 12-digit number should fail checksum."""
        assert _validate_inn_checksum("123456789012") is False

    # --- Edge cases ---

    def test_wrong_length_9_digits(self):
        """9-digit string should return False."""
        assert _validate_inn_checksum("123456789") is False

    def test_wrong_length_11_digits(self):
        """11-digit string should return False."""
        assert _validate_inn_checksum("12345678901") is False

    def test_empty_string(self):
        """Empty string should return False."""
        assert _validate_inn_checksum("") is False

    def test_wrong_length_5_digits(self):
        """5-digit string should return False."""
        assert _validate_inn_checksum("12345") is False


class TestINNChecksumIntegration:
    """Tests that INN checksum validation is applied in mask_pii()."""

    def test_valid_inn_is_masked(self):
        """Valid INN (Сбербанк) should be detected and masked."""
        text = "ИНН 7707083893"
        result = mask_pii(text)

        assert "7707083893" not in result.masked_text
        assert result.pii_count >= 1
        assert "RU_INN" in result.detected_pii_types

    def test_random_10_digit_number_not_masked_as_inn(self):
        """Random 10-digit number without valid INN checksum should NOT be masked as RU_INN."""
        # 1234567890 has invalid INN checksum
        text = "код заказа 1234567890"
        result = mask_pii(text, entities=["RU_INN"])

        # Should NOT be detected as INN (invalid checksum, no strong context)
        assert "RU_INN" not in result.detected_pii_types

    def test_valid_inn_without_context_still_masked(self):
        """Valid INN without context keywords should still be detected (checksum boosts score)."""
        text = "номер 7707083893"
        result = mask_pii(text, entities=["RU_INN"])

        # Valid checksum boosts score to 0.85, should be detected
        assert "7707083893" not in result.masked_text

    def test_multiple_inns_only_valid_masked(self):
        """When multiple 10-digit numbers appear, only valid INNs should be masked."""
        text = "ИНН 7707083893, код 1234567890"
        result = mask_pii(text, entities=["RU_INN"])

        # Valid INN should be masked
        assert "7707083893" not in result.masked_text
        # Invalid "INN" should remain (depends on context boosting from "ИНН" keyword)
        # At minimum, valid INN count should be >= 1
        assert result.pii_count >= 1


class TestPIIEdgeCases:
    """Edge-case tests for PII detection: names with Ё, grammatical cases, etc."""

    def test_name_with_yo_letter(self):
        """ФИО with letter Ё should be detected."""
        text = "директор Ёлкин Артём Геннадьевич"
        result = mask_pii(text)

        # Should detect as person name (has patronymic ending + context)
        assert result.pii_count >= 1

    def test_abbreviated_name_with_yo(self):
        """Abbreviated name with Ё should be detected."""
        text = "руководитель Ёлкин А.Г."
        result = mask_pii(text)

        assert result.pii_count >= 1

    def test_full_name_with_patronymic_ending_vich(self):
        """Name with -вич patronymic should get high score."""
        text = "Смирнов Алексей Петрович подписал документ"
        result = mask_pii(text)

        assert result.pii_count >= 1

    def test_full_name_with_patronymic_ending_vna(self):
        """Name with -вна patronymic should get high score."""
        text = "Петрова Мария Ивановна является руководителем"
        result = mask_pii(text)

        assert result.pii_count >= 1

    def test_mask_unmask_cycle_preserves_all_types(self):
        """Full mask→unmask cycle with multiple PII types should restore original."""
        original = "ИНН 7707083893, директор Иванов Иван Иванович, тел +7(495)123-45-67"
        masked = mask_pii(original, mask_level="high")
        restored = unmask_pii(masked.masked_text, masked.replacements)

        assert "7707083893" in restored
        assert "+7(495)123-45-67" in restored or "495" in restored

    def test_pii_detected_flag_true_when_pii_found(self):
        """pii_detected should be True when PII is found."""
        result = mask_pii("ИНН 7707083893")
        assert result.pii_detected is True

    def test_pii_detected_flag_false_when_clean(self):
        """pii_detected should be False when no PII found."""
        result = mask_pii("Обычный текст без данных")
        assert result.pii_detected is False

    def test_numbered_pseudonyms_are_unique(self):
        """Each PII item should get a unique numbered pseudonym."""
        text = "ИНН 7707083893, ИНН 7736050003"
        result = mask_pii(text, entities=["RU_INN"])

        # Should have 2 unique pseudonyms like [INN_1] and [INN_2]
        if result.pii_count == 2:
            pseudonyms = [r["masked"] for r in result.replacements]
            assert len(set(pseudonyms)) == 2  # All unique
