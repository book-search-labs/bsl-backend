package com.bsl.inventory.service;

public enum FailureMode {
    SUCCESS,
    FAIL_500,
    TIMEOUT,
    SUCCESS_BUT_TIMEOUT,
    RANDOM
}

