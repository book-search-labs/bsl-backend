package com.bsl.bff.api;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bsl.bff.common.ApiExceptionHandler;
import com.bsl.bff.common.BffRequestContextFilter;
import com.bsl.bff.security.AuthProperties;
import com.bsl.bff.security.AuthSessionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

@ExtendWith(MockitoExtension.class)
class AuthControllerTest {
    @Mock
    private AuthSessionService authSessionService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        AuthProperties authProperties = new AuthProperties();
        authProperties.setSessionHeader("x-session-id");
        AuthController controller = new AuthController(authSessionService, authProperties);
        mockMvc = MockMvcBuilders.standaloneSetup(controller)
            .setControllerAdvice(new ApiExceptionHandler())
            .addFilter(new BffRequestContextFilter())
            .build();
    }

    @Test
    void loginReturnsSessionPayload() throws Exception {
        when(authSessionService.login("demo@bslbooks.local", "demo1234!"))
            .thenReturn(new AuthSessionService.SessionRecord(
                "sess_abc123",
                1L,
                "demo@bslbooks.local",
                "BSL 회원",
                "WELCOME",
                "010-0000-0000",
                1760000000000L
            ));

        mockMvc.perform(post("/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"version\":\"v1\",\"email\":\"demo@bslbooks.local\",\"password\":\"demo1234!\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.session.session_id").value("sess_abc123"))
            .andExpect(jsonPath("$.session.user.user_id").value(1))
            .andExpect(jsonPath("$.session.user.email").value("demo@bslbooks.local"));
    }

    @Test
    void loginRejectsMissingCredentials() throws Exception {
        mockMvc.perform(post("/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"version\":\"v1\",\"email\":\"\",\"password\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.code").value("bad_request"));

        verify(authSessionService, never()).login(anyString(), anyString());
    }

    @Test
    void getSessionRequiresSessionHeader() throws Exception {
        mockMvc.perform(get("/auth/session"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error.code").value("unauthorized"));

        verify(authSessionService, never()).getSession(anyString());
    }

    @Test
    void logoutCallsSessionService() throws Exception {
        mockMvc.perform(post("/auth/logout")
                .header("x-session-id", "sess_abc123")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        verify(authSessionService).logout("sess_abc123");
    }
}
