CREATE TABLE positions(
 id INTEGER PRIMARY KEY,
 ticker TEXT,
 nom TEXT,
 quantite REAL,
 pru REAL,
 prix REAL,
 valeur REAL
);

CREATE TABLE transactions(
 id INTEGER PRIMARY KEY,
 date TEXT,
 ticker TEXT,
 type TEXT,
 quantite REAL,
 prix REAL,
 montant REAL
);
