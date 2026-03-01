package com.bsl.commerce.repository;

import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;

@ExtendWith(MockitoExtension.class)
class AddressRepositoryTest {

    @Mock
    private JdbcTemplate jdbcTemplate;

    @Test
    void updateAddressUpdatesAllEditableColumns() {
        AddressRepository repository = new AddressRepository(jdbcTemplate);

        repository.updateAddress(11L, "Receiver", "010-1234-5678", "12345", "Seoul Gangnam-gu", "101-202", true);

        verify(jdbcTemplate).update(
            "UPDATE user_address SET name = ?, phone = ?, zip = ?, addr1 = ?, addr2 = ?, is_default = ? WHERE address_id = ?",
            "Receiver",
            "010-1234-5678",
            "12345",
            "Seoul Gangnam-gu",
            "101-202",
            true,
            11L
        );
    }
}
