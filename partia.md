# Projekt - zarządzanie partią

#### Maksymilian Polarczyk

Schemat bazy:  

![partia](https://i.imgur.com/KGwp8hw.jpg)

## Tabele

---

1. **ID** - tabela zawierająca identyfikatory użytkowników, akcji, projektów oraz organizacji. `type` oznacza rodzaj obiektu, do którego odwołuje się identyfikator. Jest jednym z:
    * `a` - akcja
    * `u` - użytkownicy
    * `o` - organizacje
    * `p` - projekty

    typ kolumny `type` może potem zostać zastąpiony własną dziedziną.

2. **Users** - tabela zawierająca użytkowników. Zostanie dodany indeks na podstawie różnicy `upvotes - downvotes` w celu szybkiego znajdywania trolli.
    * `user_id` - klucz obcy do tabeli ID
    * `password_hash` - zaszyfrowane za pomocą modułu *pgcrypto* hasło
    * `is leader` - czy użytkownik jest liderem
    * `last_activity` - ostatnia aktywność użytkownika, używana do wyliczania zamrożonych kont
    * `upvotes`/`downvotes` - sumaryczna liczba głosów za/przeciw oddanych na akcje zaproponowane przez użytkownika

3. **Votes** - tabela zawierająca wszystkie głosy oddane przez wszystkich użytkowników, gdzie `user_id` i `action_id` to klucze obce do odpowiednich tabel.
    * `user_id` - autor głosu
    * `action_id` - akcja do której odnosi się głos
    * `is_upvote` - typ głosu: **ZA** lub **PRZECIW**

    Aby zapewnić unikalność głosów na dany projekt przez użytkowników `*_id` są kluczami głównymi. Podczas dodawania poprawnego głosu, uruchomiony zostanie wyzwalacz aktualizujący odpowiednie kolumny `upvotes`/`downvotes` w tabelach **Users** oraz **Actions**.

4. **Actions** - tabela przechowująca wszystkie utworzone akcje.
    * `*_id` - odpowiednie klucze obce identyfikujące akcję, twórcę, projekt oraz organizację.
    * `is_support` - typ akcji: **POPARCIE** lub **PROTEST**
    * `upvotes`/`downvotes` - wartości oznaczające ilość głosów **ZA** i **PRZECIW** danej akcji; dzięki nim realizacja funkcji `actions` będzie prostsza w implementacji.

    Przechowując `authority` wewnątrz tabeli **Actions** pozwalamy na niewielką redundancję danych, aby ułatwić implementację wyzwalaczy i funkcji. Indeks dla `user_id` pozwoli na szybkie aktualizowanie wartości `upvote`/`downvote` dla danego użytkownika

## Uprawnienia

---

Użytkownik **init** będzie posiadał wszystkie prawa do bazy, natomiast użytkownik **app** nie będzie mógł modyfikować tabel, więzów ani usuwać krotek.

## Implementacja

---

Każda z funkcji sprawdzać będzie, czy odpowiednie `id` odnosi się do odpowiedniego typu obiektu. Każde wywołanie funkcji zostaje zakończone błędem `AUTH_PWD` w wypadku niepoprawnego hasła dla użytkownika. Jeśli dodatkowo ostatnia akcja była wykonana przez użytkownika dawniej niż rok temu od podanego `timestamp`, akcja jest ignorowana ze statusem `USER_FROZEN`. Jeśli akcja została wykonana pomyślnie, aktuaizowana jest wartość `Users.last_activity` dla danego użytkownika. W wypadku wywołania funkcji `support`,`protest`,`upvote`,`downvote` z danymi użytkownika nie znajdującego się w bazie, tworzony jest nowy użytkownik z aktualnym timestampem.

1. `support`/`protest`:
    * Jeśli projekt istniał, odnajdź organizację dla projektu i uzupełnij nową krotkę. Jeśli nie, uzupełnij projekt o daną organizację, oraz ewentualnie dodaj nową organizację do `ID`.
2. `upvote`/`downvote`:
    * Sprawdzenie czy dana akcja istnieje. Jeśli nie - zgłaszany jest błąd `ACTION_MISSING`.
    * Jeśli głos na daną akcję został już oddany krotka nie zostanie dodana ze względu na więzy klucza głównego.
    * Samoistne uruchomienie wyzwalacza aktualizującego `upvotes`/`downvotes` dla odpowiadających krotek.
3. `actions`/`votes`/`projects`:
    * Sprawdzecznie, czy podany członek istnieje i jest liderem, Jeśli nie - zgłaszany jest błąd `AUTH_PERM`.
    * Wywołanie odpowiednich funkcji `SELECT` i agregujących dla podanych dodatkowych parametrów.
4. `trolls`:
    * Dzięki indeksowi wyliczanemu na podstawie wartości `upvotes-downvotes` w tabeli Users, funkcja SELECT będzie działać szybko.