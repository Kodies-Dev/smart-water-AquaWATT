-- Czas wszędzie: TIMESTAMPTZ = początek godziny, zapisany w UTC.

CREATE TABLE IF NOT EXISTS obiekty (
    obiekt_id      TEXT PRIMARY KEY,      -- CH_T, RU_W, RU_ZMP, RY_PNB1, RY_PZ1
    miasto         TEXT NOT NULL,
    nazwa          TEXT NOT NULL,
    opis           TEXT,
    liczba_pomp    INT,
    moc_pompy_kw   DOUBLE PRECISION,
    wydajnosc_m3h  DOUBLE PRECISION,
    zbiornik_m3    DOUBLE PRECISION,
    zrodlo_param   TEXT,                  -- skąd parametry: schemat / szacunek z danych
    stacja_pogody  TEXT                   -- punkt pogody z Open-Meteo (CH / RU / RY)
);
ALTER TABLE obiekty ADD COLUMN IF NOT EXISTS stacja_pogody TEXT;

CREATE TABLE IF NOT EXISTS energia_godz (
    obiekt_id TEXT REFERENCES obiekty,
    czas      TIMESTAMPTZ,
    kwh       DOUBLE PRECISION,
    zrodlo    TEXT,
    PRIMARY KEY (obiekt_id, czas)
);

CREATE TABLE IF NOT EXISTS energia_mies (
    obiekt_id TEXT REFERENCES obiekty,
    miesiac   DATE,
    kwh       DOUBLE PRECISION,
    zrodlo    TEXT,
    PRIMARY KEY (obiekt_id, miesiac)
);

CREATE TABLE IF NOT EXISTS przeplyw_godz (
    obiekt_id TEXT REFERENCES obiekty,
    czas      TIMESTAMPTZ,
    m3        DOUBLE PRECISION,
    PRIMARY KEY (obiekt_id, czas)
);

CREATE TABLE IF NOT EXISTS scada_godz (
    obiekt_id        TEXT REFERENCES obiekty,
    czas             TIMESTAMPTZ,
    poziom_sr        DOUBLE PRECISION,    -- poziom w zbiorniku [cm]
    poziom_max       DOUBLE PRECISION,
    przeplyw_chw_sr  DOUBLE PRECISION,    -- przepływ chwilowy [m3/h] (tylko RU_W)
    prad_p1_sr       DOUBLE PRECISION,    -- [A]
    prad_p2_sr       DOUBLE PRECISION,
    praca_pomp_h     DOUBLE PRECISION,    -- pompogodziny w tej godzinie (0..2)
    prog_start       DOUBLE PRECISION,    -- [cm]
    prog_stop        DOUBLE PRECISION,
    liczba_probek    INT,
    PRIMARY KEY (obiekt_id, czas)
);

CREATE TABLE IF NOT EXISTS opad_godz (
    stacja TEXT,                          -- RU = deszczomierz na oczyszczalni w Rudzie Śl.
    czas   TIMESTAMPTZ,
    mm     DOUBLE PRECISION,
    PRIMARY KEY (stacja, czas)
);

CREATE TABLE IF NOT EXISTS pogoda_godz (     -- Open-Meteo, archiwum ERA5
    stacja           TEXT,
    czas             TIMESTAMPTZ,
    temp_c           DOUBLE PRECISION,
    opad_mm          DOUBLE PRECISION,
    deszcz_mm        DOUBLE PRECISION,
    snieg_cm         DOUBLE PRECISION,
    pokrywa_m        DOUBLE PRECISION,
    wilg_gleby_0_7   DOUBLE PRECISION,
    wilg_gleby_7_28  DOUBLE PRECISION,
    et0_mm           DOUBLE PRECISION,
    PRIMARY KEY (stacja, czas)
);

CREATE TABLE IF NOT EXISTS kalendarz (
    data               DATE PRIMARY KEY,      -- data lokalna
    dzien_tyg          SMALLINT,              -- 0 = poniedziałek
    weekend            BOOLEAN,
    swieto             BOOLEAN,
    nazwa_swieta       TEXT,
    dzien_wolny        BOOLEAN,               -- weekend lub święto
    mostek             BOOLEAN,               -- dzień roboczy między dwoma wolnymi
    ferie_zimowe       BOOLEAN,               -- woj. śląskie
    wakacje            BOOLEAN,
    przerwa_swiateczna BOOLEAN
);

CREATE TABLE IF NOT EXISTS alarmy (
    obiekt_id TEXT REFERENCES obiekty,
    czas      TIMESTAMPTZ,
    sygnal    TEXT,                       -- np. spietrzenie, awaria_P1
    stan      SMALLINT                    -- 1 = aktywny, 0 = nieaktywny
);

CREATE TABLE IF NOT EXISTS etl_log (
    uruchomienie TIMESTAMPTZ,
    krok         TEXT,
    obiekt_id    TEXT,
    wiersze_wej  BIGINT,
    wiersze_wyj  BIGINT,
    uwagi        TEXT
);

-- Widok pod model: energia + wszystko, co pasuje w tej samej godzinie.
DROP VIEW IF EXISTS v_model;
CREATE VIEW v_model AS
SELECT e.obiekt_id, o.miasto, e.czas, e.czas AT TIME ZONE 'Europe/Warsaw' AS czas_lokalny, e.kwh,
       p.m3, s.praca_pomp_h, s.poziom_sr, s.poziom_max, s.przeplyw_chw_sr,
       op.mm AS opad_ru_mm,
       pw.opad_mm AS opad_om_mm, pw.temp_c, pw.snieg_cm, pw.pokrywa_m,
       pw.wilg_gleby_0_7, pw.wilg_gleby_7_28, pw.et0_mm,
       k.dzien_wolny, k.swieto, k.mostek, k.ferie_zimowe, k.wakacje, k.przerwa_swiateczna
FROM energia_godz e
JOIN obiekty o USING (obiekt_id)
LEFT JOIN przeplyw_godz p USING (obiekt_id, czas)
LEFT JOIN scada_godz s USING (obiekt_id, czas)
LEFT JOIN opad_godz op ON op.stacja = 'RU' AND op.czas = e.czas
LEFT JOIN pogoda_godz pw ON pw.stacja = o.stacja_pogody AND pw.czas = e.czas
LEFT JOIN kalendarz k ON k.data = (e.czas AT TIME ZONE 'Europe/Warsaw')::date;
