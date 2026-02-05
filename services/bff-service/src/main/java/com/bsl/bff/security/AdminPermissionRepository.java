package com.bsl.bff.security;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AdminPermissionRepository {
    private final JdbcTemplate jdbcTemplate;

    public AdminPermissionRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Set<String> findPermissions(String adminId) {
        List<String> perms = jdbcTemplate.queryForList(
            "SELECT rp.perm "
                + "FROM admin_role ar "
                + "JOIN role_permission rp ON ar.role_id = rp.role_id "
                + "WHERE ar.admin_id = ?",
            String.class,
            adminId
        );
        return new HashSet<>(perms);
    }
}
