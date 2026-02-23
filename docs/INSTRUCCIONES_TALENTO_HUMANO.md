# Instrucciones para Talento Humano - Prueba Tecnica Odoo Senior

## Enviar al candidato 1 dia antes de la prueba

---

### Mensaje sugerido (email/WhatsApp):

> Hola [Nombre],
>
> Manana realizaremos la prueba tecnica para el cargo de Desarrollador Odoo Senior.
>
> **Duracion:** 2 horas
>
> **Requisitos previos (instalar antes de la prueba):**
>
> 1. **Docker Desktop** - https://www.docker.com/products/docker-desktop/
>    - Windows: requiere WSL2 habilitado
>    - Mac: funciona en Intel y Apple Silicon
>    - Linux: Docker Engine + Docker Compose
>
> 2. **Git** - https://git-scm.com/downloads
>
> 3. **Editor de codigo** (el que prefiera: VS Code, PyCharm, etc.)
>
> 4. **Minimo 4 GB de RAM disponibles** para los contenedores Docker
>
> 5. **Puerto 8079 disponible** (verificar que no haya otro servicio corriendo ahi)
>
> **Para verificar que todo funciona, ejecutar en terminal:**
> ```
> docker --version
> docker-compose --version
> git --version
> ```
>
> El dia de la prueba se le compartira el enlace al repositorio con las instrucciones completas.
>
> **Herramientas permitidas durante la prueba:** Claude Code, Copilot, ChatGPT, documentacion online, etc.
>
> **Importante:** No es necesario tener experiencia previa con el modulo especifico. Se evaluara la capacidad de analisis, debugging y desarrollo en Odoo 14.
>
> Quedo atento a cualquier duda.

---

### El dia de la prueba

1. Compartir el enlace del repositorio: https://github.com/Santiago8659/technical-exam-odoo
2. El candidato clona, levanta Docker y tiene todo listo en ~3 minutos
3. Las instrucciones completas estan en el README del repositorio

### Que debe entregar el candidato

1. Los archivos modificados (diff, patch, o rama en su fork)
2. Un documento breve (.md o .txt) explicando sus soluciones
3. Cualquier nota adicional sobre decisiones de diseno

### Despues de la prueba

- Coordinar la defensa oral (30 min aprox) donde se preguntara sobre decisiones tecnicas
- El evaluador debe usar el documento `EVALUATION_RUBRIC.md` (solo acceso interno, no esta en el repo)