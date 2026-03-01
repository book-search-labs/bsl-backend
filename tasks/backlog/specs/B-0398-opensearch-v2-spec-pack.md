# B-0398 Spec Pack — OpenSearch v2 Schema + Query DSL

이 문서는 `B-0398` 구현의 **정식 스펙 원문**이다.
구현/리뷰 시 본 문서의 JSON 템플릿을 기준으로 한다.

## 0) Preconditions

- OpenSearch plugin
  - `analysis-icu`
  - `analysis-nori`
- OpenSearch config files
  - `analysis/userdict_ko.txt`
  - `analysis/synonyms_ko.txt`
  - `analysis/synonyms_en.txt`

## 1) books_doc v2

### 1.1 Index create body

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "refresh_interval": "1s",
    "analysis": {
      "char_filter": {
        "cf_punct_to_space": {
          "type": "pattern_replace",
          "pattern": "[\\s\\u00A0]+|[“”‘’`´]|[·•‧ㆍ・]|[\\-_/\\\\.,:;!?()\\[\\]{}]+",
          "replacement": " "
        },
        "cf_ws_collapse": {
          "type": "pattern_replace",
          "pattern": "\\s+",
          "replacement": " "
        },
        "cf_compact": {
          "type": "pattern_replace",
          "pattern": "[\\s\\u00A0]+|[“”‘’`´]|[·•‧ㆍ・]|[\\-_/\\\\.,:;!?()\\[\\]{}]+",
          "replacement": ""
        },
        "cf_isbn_keep_digits": {
          "type": "pattern_replace",
          "pattern": "[^0-9\\p{Nd}Xx]+",
          "replacement": ""
        }
      },
      "tokenizer": {
        "ko_nori_userdict": {
          "type": "nori_tokenizer",
          "decompound_mode": "mixed",
          "discard_punctuation": true,
          "user_dictionary": "analysis/userdict_ko.txt"
        }
      },
      "filter": {
        "ko_pos": {
          "type": "nori_part_of_speech",
          "stoptags": [
            "E",
            "IC",
            "J",
            "MAG",
            "MAJ",
            "MM",
            "SP",
            "SSC",
            "SSO",
            "SC",
            "SE",
            "XPN",
            "XSA",
            "XSN",
            "XSV",
            "UNA",
            "NA",
            "VSV"
          ]
        },
        "en_stop": { "type": "stop", "stopwords": "_english_" },
        "en_possessive": { "type": "stemmer", "language": "possessive_english" },
        "en_stem": { "type": "stemmer", "language": "english" },

        "syn_ko": { "type": "synonym_graph", "synonyms_path": "analysis/synonyms_ko.txt" },
        "syn_en": { "type": "synonym_graph", "synonyms_path": "analysis/synonyms_en.txt" }
      },
      "normalizer": {
        "keyword_norm": {
          "type": "custom",
          "char_filter": [],
          "filter": ["icu_folding", "trim"]
        },
        "isbn_norm": {
          "type": "custom",
          "char_filter": ["cf_isbn_keep_digits"],
          "filter": ["decimal_digit", "uppercase", "trim"]
        }
      },
      "analyzer": {
        "ko_text_index": {
          "type": "custom",
          "char_filter": ["cf_punct_to_space", "cf_ws_collapse"],
          "tokenizer": "ko_nori_userdict",
          "filter": ["nori_readingform", "icu_folding", "ko_pos"]
        },
        "ko_text_search": {
          "type": "custom",
          "char_filter": ["cf_punct_to_space", "cf_ws_collapse"],
          "tokenizer": "ko_nori_userdict",
          "filter": ["nori_readingform", "icu_folding", "ko_pos", "syn_ko"]
        },

        "en_text_index": {
          "type": "custom",
          "char_filter": ["cf_punct_to_space", "cf_ws_collapse"],
          "tokenizer": "standard",
          "filter": ["icu_folding", "en_stop", "en_possessive", "en_stem"]
        },
        "en_text_search": {
          "type": "custom",
          "char_filter": ["cf_punct_to_space", "cf_ws_collapse"],
          "tokenizer": "standard",
          "filter": ["icu_folding", "syn_en", "en_stop", "en_possessive", "en_stem"]
        },

        "univ_auto_index": {
          "type": "custom",
          "char_filter": ["cf_punct_to_space", "cf_ws_collapse"],
          "tokenizer": "standard",
          "filter": ["icu_folding"]
        },
        "univ_auto_search": {
          "type": "custom",
          "char_filter": ["cf_punct_to_space", "cf_ws_collapse"],
          "tokenizer": "standard",
          "filter": ["icu_folding"]
        },

        "univ_compact_index": {
          "type": "custom",
          "char_filter": ["cf_compact"],
          "tokenizer": "keyword",
          "filter": ["icu_folding"]
        },
        "univ_compact_search": {
          "type": "custom",
          "char_filter": ["cf_compact"],
          "tokenizer": "keyword",
          "filter": ["icu_folding"]
        }
      }
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "doc_id": { "type": "keyword" },

      "title_ko": {
        "type": "text",
        "analyzer": "ko_text_index",
        "search_analyzer": "ko_text_search",
        "index_phrases": true,
        "fields": {
          "exact": { "type": "keyword", "normalizer": "keyword_norm" },
          "auto": {
            "type": "text",
            "analyzer": "univ_auto_index",
            "search_analyzer": "univ_auto_search",
            "index_prefixes": { "min_chars": 2, "max_chars": 20 }
          },
          "compact": { "type": "text", "analyzer": "univ_compact_index", "search_analyzer": "univ_compact_search" }
        }
      },

      "title_en": {
        "type": "text",
        "analyzer": "en_text_index",
        "search_analyzer": "en_text_search",
        "index_phrases": true,
        "fields": {
          "exact": { "type": "keyword", "normalizer": "keyword_norm" },
          "auto": {
            "type": "text",
            "analyzer": "univ_auto_index",
            "search_analyzer": "univ_auto_search",
            "index_prefixes": { "min_chars": 2, "max_chars": 20 }
          },
          "compact": { "type": "text", "analyzer": "univ_compact_index", "search_analyzer": "univ_compact_search" }
        }
      },

      "series_name": {
        "type": "text",
        "analyzer": "univ_auto_index",
        "search_analyzer": "univ_auto_search",
        "fields": {
          "exact": { "type": "keyword", "normalizer": "keyword_norm" },
          "auto": {
            "type": "text",
            "analyzer": "univ_auto_index",
            "search_analyzer": "univ_auto_search",
            "index_prefixes": { "min_chars": 2, "max_chars": 20 }
          },
          "compact": { "type": "text", "analyzer": "univ_compact_index", "search_analyzer": "univ_compact_search" }
        }
      },

      "author_names_ko": {
        "type": "text",
        "analyzer": "ko_text_index",
        "search_analyzer": "ko_text_search",
        "fields": {
          "exact": { "type": "keyword", "normalizer": "keyword_norm" },
          "auto": {
            "type": "text",
            "analyzer": "univ_auto_index",
            "search_analyzer": "univ_auto_search",
            "index_prefixes": { "min_chars": 2, "max_chars": 20 }
          },
          "compact": { "type": "text", "analyzer": "univ_compact_index", "search_analyzer": "univ_compact_search" }
        }
      },

      "author_names_en": {
        "type": "text",
        "analyzer": "en_text_index",
        "search_analyzer": "en_text_search",
        "fields": {
          "exact": { "type": "keyword", "normalizer": "keyword_norm" },
          "auto": {
            "type": "text",
            "analyzer": "univ_auto_index",
            "search_analyzer": "univ_auto_search",
            "index_prefixes": { "min_chars": 2, "max_chars": 20 }
          },
          "compact": { "type": "text", "analyzer": "univ_compact_index", "search_analyzer": "univ_compact_search" }
        }
      },

      "authors": {
        "type": "nested",
        "properties": {
          "agent_id": { "type": "keyword" },
          "name_ko": { "type": "keyword", "normalizer": "keyword_norm" },
          "name_en": { "type": "keyword", "normalizer": "keyword_norm" },
          "role": { "type": "keyword" },
          "ord": { "type": "short" }
        }
      },

      "publisher_name": {
        "type": "text",
        "analyzer": "univ_auto_index",
        "search_analyzer": "univ_auto_search",
        "fields": {
          "exact": { "type": "keyword", "normalizer": "keyword_norm" },
          "auto": {
            "type": "text",
            "analyzer": "univ_auto_index",
            "search_analyzer": "univ_auto_search",
            "index_prefixes": { "min_chars": 2, "max_chars": 20 }
          },
          "compact": { "type": "text", "analyzer": "univ_compact_index", "search_analyzer": "univ_compact_search" }
        }
      },

      "identifiers": {
        "properties": {
          "isbn13": { "type": "keyword", "normalizer": "isbn_norm" },
          "isbn10": { "type": "keyword", "normalizer": "isbn_norm" }
        }
      },

      "language_code": { "type": "keyword" },
      "issued_year": { "type": "short" },
      "volume": { "type": "short" },
      "edition_labels": { "type": "keyword" },

      "kdc_node_id": { "type": "long" },
      "kdc_code": { "type": "keyword" },
      "kdc_edition": { "type": "keyword" },
      "kdc_path_codes": { "type": "keyword" },
      "category_paths": { "type": "keyword" },
      "concept_ids": { "type": "keyword" },

      "is_hidden": { "type": "boolean" },
      "redirect_to": { "type": "keyword" },
      "updated_at": { "type": "date" }
    }
  }
}
```

### 1.2 Aliases

```json
{
  "actions": [
    { "add": { "index": "books_doc_v2_YYYYMMDD_001", "alias": "books_doc_read" } },
    { "add": { "index": "books_doc_v2_YYYYMMDD_001", "alias": "books_doc_write", "is_write_index": true } }
  ]
}
```

### 1.3 Ingest requirements

- `series_name`: 값 없으면 미포함
- `author_names_ko`: `authors[].name_ko`를 string[]로 집계
- `author_names_en`: `authors[].name_en`를 string[]로 집계

## 2) ac_candidates v2

### 2.1 Index create body

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "refresh_interval": "1s",
    "analysis": {
      "char_filter": {
        "cf_punct_to_space": {
          "type": "pattern_replace",
          "pattern": "[\\s\\u00A0]+|[“”‘’`´]|[·•‧ㆍ・]|[\\-_/\\\\.,:;!?()\\[\\]{}]+",
          "replacement": " "
        },
        "cf_ws_collapse": {
          "type": "pattern_replace",
          "pattern": "\\s+",
          "replacement": " "
        },
        "cf_compact": {
          "type": "pattern_replace",
          "pattern": "[\\s\\u00A0]+|[“”‘’`´]|[·•‧ㆍ・]|[\\-_/\\\\.,:;!?()\\[\\]{}]+",
          "replacement": ""
        }
      },
      "normalizer": {
        "keyword_norm": {
          "type": "custom",
          "filter": ["icu_folding", "trim"]
        },
        "keyword_compact_norm": {
          "type": "custom",
          "char_filter": ["cf_compact"],
          "filter": ["icu_folding", "trim"]
        }
      },
      "analyzer": {
        "ac_auto_index": {
          "type": "custom",
          "char_filter": ["cf_punct_to_space", "cf_ws_collapse"],
          "tokenizer": "standard",
          "filter": ["icu_folding"]
        },
        "ac_auto_search": {
          "type": "custom",
          "char_filter": ["cf_punct_to_space", "cf_ws_collapse"],
          "tokenizer": "standard",
          "filter": ["icu_folding"]
        },
        "ac_compact_index": {
          "type": "custom",
          "char_filter": ["cf_compact"],
          "tokenizer": "keyword",
          "filter": ["icu_folding"]
        },
        "ac_compact_search": {
          "type": "custom",
          "char_filter": ["cf_compact"],
          "tokenizer": "keyword",
          "filter": ["icu_folding"]
        }
      }
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "suggest_id": { "type": "keyword" },
      "type": { "type": "keyword" },
      "lang": { "type": "keyword" },

      "text": {
        "type": "text",
        "analyzer": "ac_auto_index",
        "search_analyzer": "ac_auto_search",
        "index_prefixes": { "min_chars": 2, "max_chars": 20 },
        "fields": {
          "exact": { "type": "keyword", "normalizer": "keyword_norm" },
          "compact": { "type": "text", "analyzer": "ac_compact_index", "search_analyzer": "ac_compact_search" },
          "compact_kw": { "type": "keyword", "normalizer": "keyword_compact_norm" }
        }
      },

      "target_doc_id": { "type": "keyword" },
      "target_id": { "type": "keyword" },

      "weight": { "type": "integer" },
      "clicks_7d": { "type": "float" },
      "impressions_7d": { "type": "float" },
      "ctr_7d": { "type": "float" },
      "popularity_7d": { "type": "float" },

      "is_blocked": { "type": "boolean" },
      "last_seen_at": { "type": "date" },
      "updated_at": { "type": "date" },

      "payload": { "type": "object", "enabled": false }
    }
  }
}
```

### 2.2 Aliases

```json
{
  "actions": [
    { "add": { "index": "ac_candidates_v2_YYYYMMDD_001", "alias": "ac_candidates_read" } },
    { "add": { "index": "ac_candidates_v2_YYYYMMDD_001", "alias": "ac_candidates_write", "is_write_index": true } }
  ]
}
```

## 3) books_vec v5

### 3.1 Index create body

```json
{
  "settings": {
    "index": {
      "knn": true
    },
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "refresh_interval": "1s"
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "doc_id": { "type": "keyword" },

      "embedding": {
        "type": "knn_vector",
        "dimension": 384,
        "method": {
          "engine": "lucene",
          "space_type": "cosinesimil",
          "name": "hnsw",
          "parameters": {
            "ef_construction": 128,
            "m": 16
          }
        }
      },

      "is_hidden": { "type": "boolean" },
      "language_code": { "type": "keyword" },

      "issued_year": { "type": "short" },
      "volume": { "type": "short" },
      "edition_labels": { "type": "keyword" },

      "kdc_node_id": { "type": "long" },
      "kdc_code": { "type": "keyword" },
      "kdc_edition": { "type": "keyword" },
      "kdc_path_codes": { "type": "keyword" },

      "category_paths": { "type": "keyword" },
      "concept_ids": { "type": "keyword" },

      "identifiers": {
        "properties": {
          "isbn13": { "type": "keyword" },
          "isbn10": { "type": "keyword" }
        }
      },

      "updated_at": { "type": "date" },
      "vector_text_hash": { "type": "keyword" },
      "vector_text_v2": { "type": "text", "index": false }
    }
  }
}
```

### 3.2 Aliases

```json
{
  "actions": [
    { "add": { "index": "books_vec_v5_YYYYMMDD_001", "alias": "books_vec_read" } },
    { "add": { "index": "books_vec_v5_YYYYMMDD_001", "alias": "books_vec_write", "is_write_index": true } }
  ]
}
```

## 4) /search DSL templates (1~10)

### 4.1 (1) Lexical default

```json
{
  "size": "<topK>",
  "track_total_hits": false,
  "query": {
    "bool": {
      "filter": [
        { "term": { "is_hidden": false } },
        "<optional filters: append objects here>"
      ],
      "should": [
        {
          "multi_match": {
            "query": "<q>",
            "type": "best_fields",
            "fields": [
              "title_ko^8",
              "title_en^7",
              "series_name^4",
              "author_names_ko^3",
              "author_names_en^2.5",
              "publisher_name^2"
            ],
            "operator": "<optional: and|or>",
            "minimum_should_match": "<optional>",
            "lenient": true
          }
        },
        {
          "dis_max": {
            "tie_breaker": 0.2,
            "queries": [
              { "match_phrase": { "title_ko": { "query": "<trimmed q>", "slop": 1, "boost": 15.0 } } },
              { "match_phrase": { "title_en": { "query": "<trimmed q>", "slop": 1, "boost": 12.0 } } },
              { "match_phrase": { "series_name": { "query": "<trimmed q>", "slop": 1, "boost": 6.0 } } }
            ]
          }
        },
        {
          "multi_match": {
            "query": "<q>",
            "type": "best_fields",
            "fields": [
              "title_ko.compact^6",
              "title_en.compact^5",
              "series_name.compact^3",
              "author_names_ko.compact^2.5",
              "author_names_en.compact^2.0",
              "publisher_name.compact^2"
            ],
            "operator": "or",
            "lenient": true
          }
        },
        {
          "multi_match": {
            "query": "<q>",
            "type": "bool_prefix",
            "fields": [
              "title_ko.auto^4",
              "title_en.auto^3.5",
              "series_name.auto^2.8",
              "author_names_ko.auto^2.2",
              "author_names_en.auto^1.8",
              "publisher_name.auto^1.8"
            ],
            "lenient": true
          }
        }
      ],
      "minimum_should_match": 1
    }
  },
  "explain": "<optional true>"
}
```

### 4.2 (2) Lexical override (ISBN route)

```json
{
  "size": "<topK>",
  "track_total_hits": false,
  "query": {
    "bool": {
      "filter": [
        { "term": { "is_hidden": false } },
        "<optional filters: append objects here>"
      ],
      "must": [
        {
          "bool": {
            "should": [
              { "term": { "identifiers.isbn13": "<isbn_norm>" } },
              { "term": { "identifiers.isbn10": "<isbn_norm>" } }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "should": [
        {
          "dis_max": {
            "tie_breaker": 0.2,
            "queries": [
              {
                "multi_match": {
                  "query": "<residual>",
                  "type": "best_fields",
                  "fields": [
                    "title_ko^3",
                    "title_en^2.5",
                    "series_name^2",
                    "publisher_name^1.8",
                    "author_names_ko^1.6",
                    "author_names_en^1.4"
                  ],
                  "operator": "or",
                  "lenient": true
                }
              },
              {
                "multi_match": {
                  "query": "<residual>",
                  "type": "best_fields",
                  "fields": [
                    "title_ko.compact^2.2",
                    "title_en.compact^2.0",
                    "series_name.compact^1.6",
                    "publisher_name.compact^1.4",
                    "author_names_ko.compact^1.4"
                  ],
                  "operator": "or",
                  "lenient": true
                }
              },
              {
                "multi_match": {
                  "query": "<residual>",
                  "type": "bool_prefix",
                  "fields": [
                    "title_ko.auto^1.8",
                    "title_en.auto^1.6",
                    "series_name.auto^1.3",
                    "publisher_name.auto^1.2",
                    "author_names_ko.auto^1.2"
                  ],
                  "lenient": true
                }
              }
            ]
          }
        }
      ],
      "minimum_should_match": 0
    }
  }
}
```

### 4.3 (3) Lexical override (entity blocks)

```json
{
  "size": "<topK>",
  "track_total_hits": false,
  "query": {
    "bool": {
      "filter": [
        { "term": { "is_hidden": false } },
        "<optional filters: append objects here>"
      ],
      "must": [
        {
          "bool": {
            "should": [
              { "match": { "author_names_ko": { "query": "<author>", "boost": 3.0 } } },
              { "match": { "author_names_ko.compact": { "query": "<author>", "boost": 2.2 } } },
              { "match": { "author_names_en": { "query": "<author>", "boost": 1.8 } } },
              { "multi_match": { "query": "<author>", "type": "bool_prefix", "fields": ["author_names_ko.auto^1.6", "author_names_en.auto^1.3"] } }
            ],
            "minimum_should_match": 1
          }
        },
        {
          "bool": {
            "should": [
              { "match": { "title_ko": { "query": "<title>", "boost": 3.0 } } },
              { "match": { "title_ko.compact": { "query": "<title>", "boost": 2.2 } } },
              { "match_phrase": { "title_ko": { "query": "<title>", "slop": 1, "boost": 6.0 } } },
              { "multi_match": { "query": "<title>", "type": "bool_prefix", "fields": ["title_ko.auto^1.8", "title_en.auto^1.5"] } }
            ],
            "minimum_should_match": 1
          }
        },
        {
          "bool": {
            "should": [
              { "match": { "series_name": { "query": "<series>", "boost": 2.5 } } },
              { "match": { "series_name.compact": { "query": "<series>", "boost": 1.9 } } },
              { "match_phrase": { "series_name": { "query": "<series>", "slop": 1, "boost": 4.0 } } },
              { "multi_match": { "query": "<series>", "type": "bool_prefix", "fields": ["series_name.auto^1.6"] } }
            ],
            "minimum_should_match": 1
          }
        },
        {
          "bool": {
            "should": [
              { "match": { "publisher_name": { "query": "<publisher>", "boost": 2.0 } } },
              { "match": { "publisher_name.compact": { "query": "<publisher>", "boost": 1.5 } } },
              { "multi_match": { "query": "<publisher>", "type": "bool_prefix", "fields": ["publisher_name.auto^1.4"] } }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "should": [
        {
          "multi_match": {
            "query": "<residual>",
            "type": "best_fields",
            "fields": [
              "title_ko^2",
              "title_en^1.6",
              "series_name^1.4",
              "publisher_name^1.2",
              "author_names_ko^1.2",
              "author_names_en^1.1"
            ],
            "operator": "or",
            "lenient": true
          }
        }
      ],
      "minimum_should_match": 0
    }
  }
}
```

### 4.4 (4) filter-only

```json
{
  "size": "<topK>",
  "track_total_hits": false,
  "query": {
    "bool": {
      "filter": [
        { "term": { "is_hidden": false } },
        "<optional filters: append objects here>"
      ],
      "must": [{ "match_all": {} }]
    }
  },
  "explain": "<optional true>"
}
```

### 4.5 (5) vector knn embedding

```json
{
  "size": "<topK>",
  "track_total_hits": false,
  "_source": ["doc_id"],
  "query": {
    "knn": {
      "embedding": {
        "vector": ["<embedded query vector>"],
        "k": "<topK>",
        "filter": {
          "bool": {
            "filter": [
              { "term": { "is_hidden": false } },
              "<optional filters: append objects here>"
            ]
          }
        }
      }
    }
  },
  "explain": "<optional true>"
}
```

### 4.6 (6) vector neural

```json
{
  "size": "<topK>",
  "track_total_hits": false,
  "_source": ["doc_id"],
  "query": {
    "neural": {
      "embedding": {
        "query_text": "<q>",
        "model_id": "<SEARCH_VECTOR_MODEL_ID>",
        "k": "<topK>",
        "filter": {
          "bool": {
            "filter": [
              { "term": { "is_hidden": false } },
              "<optional filters: append objects here>"
            ]
          }
        }
      }
    }
  },
  "explain": "<optional true>"
}
```

### 4.7 (7) chunk knn

```json
{
  "size": "<topK>",
  "track_total_hits": false,
  "query": {
    "knn": {
      "embedding": {
        "vector": ["<embedded query vector>"],
        "k": "<topK>",
        "filter": {
          "bool": {
            "filter": [
              "<optional filters: append objects here>"
            ]
          }
        }
      }
    }
  },
  "explain": "<optional true>"
}
```

### 4.8 (8) hydrate

```json
{ "ids": ["<doc_id_1>", "<doc_id_2>", "<doc_id_3>"] }
```

### 4.9 (9) detail

```http
GET /books_doc_read/_doc/<docId>
```

### 4.10 (10) optional filters mapping

```json
{ "term":  { "volume": "<int>" } }
{ "term":  { "edition_labels": "<value>" } }
{ "terms": { "edition_labels": ["<v1>", "<v2>"] } }
{ "term":  { "identifiers.isbn13": "<isbn_norm>" } }
{ "term":  { "language_code": "<value>" } }
{ "term":  { "kdc_node_id": "<value>" } }
{ "terms": { "kdc_node_id": ["<v1>", "<v2>"] } }
{ "term":  { "kdc_code": "<value>" } }
{ "terms": { "kdc_code": ["<v1>", "<v2>"] } }
{ "term":  { "kdc_path_codes": "<value>" } }
{ "terms": { "kdc_path_codes": ["<v1>", "<v2>"] } }
{ "term":  { "kdc_edition": "<value>" } }
```

## 5) Autocomplete DSL (ac_candidates v2)

```json
{
  "size": 10,
  "_source": ["suggest_id", "type", "lang", "text", "target_doc_id", "target_id", "weight"],
  "query": {
    "function_score": {
      "query": {
        "bool": {
          "filter": [
            { "term": { "is_blocked": false } },
            "<optional filters: lang/type 등 append>"
          ],
          "should": [
            {
              "multi_match": {
                "query": "<q>",
                "type": "bool_prefix",
                "fields": ["text^3"]
              }
            },
            {
              "match": {
                "text.compact": {
                  "query": "<q>",
                  "boost": 1.5
                }
              }
            }
          ],
          "minimum_should_match": 1
        }
      },
      "score_mode": "sum",
      "boost_mode": "sum",
      "functions": [
        { "field_value_factor": { "field": "weight", "factor": 0.01, "missing": 0 } },
        { "field_value_factor": { "field": "popularity_7d", "factor": 0.1, "missing": 0 } },
        { "field_value_factor": { "field": "ctr_7d", "factor": 1.0, "missing": 0 } },
        { "gauss": { "last_seen_at": { "origin": "now", "scale": "14d", "decay": 0.5 } } }
      ]
    }
  }
}
```
