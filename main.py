import streamlit as st
import requests
import pandas as pd
from decouple import config
from io import BytesIO

API_URL = 'https://canvas.uautonoma.cl/api/v1'
ACCESS_TOKEN = config('TOKEN')  # Reemplaza con tu token de acceso

st.set_page_config(page_title="Grades Wizard", layout="wide", page_icon="🚀")

headers = {
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}

def obtener_notas_curso(COURSE_ID):
    # Obtener la lista de IDs y nombres de los estudiantes
    students = []
    url = f'{API_URL}/courses/{COURSE_ID}/students'
    params = {'per_page': 100}
    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            st.error(f'Error al obtener estudiantes del curso {COURSE_ID}: {response.text}')
            return None
        students.extend(response.json())
        url = response.links.get('next', {}).get('url')
    if not students:
        st.warning(f'No se encontraron estudiantes para el curso {COURSE_ID}')
        return None
    student_ids = [s['id'] for s in students if s['name'] != 'Estudiante de prueba']
    student_names = {s['id']: s['name'] for s in students if s['name'] != 'Estudiante de prueba'}

    # Obtener la lista de tareas (assignments) y sus nombres
    assignments = []
    url = f'{API_URL}/courses/{COURSE_ID}/assignments'
    params = {'per_page': 100}
    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            st.error(f'Error al obtener tareas del curso {COURSE_ID}: {response.text}')
            return None
        assignments.extend(response.json())
        url = response.links.get('next', {}).get('url')
    if not assignments:
        st.warning(f'No se encontraron tareas para el curso {COURSE_ID}')
        return None
    assignment_names = {a['id']: a['name'] for a in assignments}

    # Obtener las inscripciones para extraer las notas finales
    enrollments = []
    url = f'{API_URL}/courses/{COURSE_ID}/enrollments'
    params = {'type[]': 'StudentEnrollment', 'state[]': 'active', 'per_page': 100}
    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            st.error(f'Error al obtener inscripciones del curso {COURSE_ID}: {response.text}')
            return None
        enrollments.extend(response.json())
        url = response.links.get('next', {}).get('url')

    # Crear diccionarios con las notas finales de cada estudiante
    final_grades = {}
    final_scores = {}
    user_emails = {}
    for enrollment in enrollments:
        user_id = enrollment['user_id']
        grades = enrollment.get('grades', {})
        user_emails[user_id] = enrollment['user']['login_id']
        final_grade = grades.get('final_grade')  # Nota final en formato numérico
        final_score = grades.get('final_score')  # Porcentaje final
        try:
            final_grades[user_id] = float(final_grade) if final_grade is not None else None
        except (ValueError, TypeError):
            final_grades[user_id] = None
        final_scores[user_id] = f"{final_score}%" if final_score is not None else None

    # Configurar los parámetros de la solicitud para las submissions
    url = f'{API_URL}/courses/{COURSE_ID}/students/submissions'
    params = {
        'include[]': 'sub_assignment_submissions',
        'exclude_response_fields[]': [
            'preview_url', 'external_tool_url', 'url', 'attachments', 'attempt',
            'cached_due_date', 'sticker', 'submitted_at', 'redo_request',
            'late_policy_status', 'late', 'points_deducted', 'posted_at',
            'proxy_submitter', 'proxy_submitter_id', 'seconds_late', 'excused',
            'grading_period_id', 'grade_matches_current_submission',
        ],
        'grouped': 1,
        'response_fields[]': [
            'assignment_id',
            'custom_grade_status_id', 'entered_grade', 'entered_score',
            'grade', 'id', 'missing', 'score', 'submission_type', 'user_id',
            'workflow_state'
        ],
        'student_ids[]': student_ids,
        'per_page': 100
    }

    # Obtener las submissions
    submissions = []
    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            st.error(f'Error al obtener submissions del curso {COURSE_ID}: {response.text}')
            return None
        submissions.extend(response.json())
        url = response.links.get('next', {}).get('url')

    # Construir la tabla
    data = []
    for student in submissions:
        student_id = student['user_id']
        student_name = student_names.get(student_id, 'Desconocido').capitalize()
        student_sis_user_id = student.get('sis_user_id', 'Desconocido')
        rut = student_sis_user_id[:-1] + '-' + student_sis_user_id[-1] if student_sis_user_id != 'Desconocido' else 'Desconocido'
        student_email = user_emails.get(student_id, 'Desconocido').lower()
        row = {'Estudiante': student_name, 'Rut': rut, 'Email': student_email}
        for submission in student['submissions']:
            assignment_id = submission['assignment_id']
            assignment_name = assignment_names.get(assignment_id, f'Tarea {assignment_id}')
            grade = submission.get('grade')
            if grade is not None:
                try:
                    grade = float(grade)
                except ValueError:
                    pass  # Mantener el valor original si no se puede convertir
            else:
                grade = None
            row[assignment_name] = grade
        # Agregar las notas finales al registro
        row['Porcentaje'] = final_scores.get(student_id)
        row['Nota'] = final_grades.get(student_id)
        data.append(row)

    df = pd.DataFrame(data)
    df = df.drop(columns='Autoevaluación') if 'Autoevaluación' in df.columns else df
    if df.empty:
        st.warning(f'No se encontraron calificaciones para el curso {COURSE_ID}')
        return None
    df = df.set_index('Estudiante')
    # Ordenar los estudiantes de forma alfabética
    df = df.sort_index()
    return df

def course_info(COURSE_ID):
    response = requests.get(f"{API_URL}/courses/{COURSE_ID}", headers=headers)
    if response.status_code == 200:
        info = response.json()
        return info
    else:
        print(f"Error al obtener información del curso {COURSE_ID}: {response.status_code}")
        return None

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Escribir el DataFrame al archivo Excel sin formatos
        df.to_excel(writer, sheet_name='Calificaciones', index=True, header=True)
        workbook = writer.book
        worksheet = writer.sheets['Calificaciones']

        # Ajustar anchos de columna
        for idx, col in enumerate(df.columns):
            # Obtener el ancho máximo entre el contenido y el nombre de la columna
            max_len = max(
                df[col].astype(str).map(len).max(),
                len(str(col))
            ) + 2  # Añadir un poco de espacio extra
            worksheet.set_column(idx + 1, idx + 1, max_len)

        # Ajustar ancho de la columna índice
        max_len = max(
            df.index.astype(str).map(len).max(),
            len(str(df.index.name)) if df.index.name else 0
        ) + 2
        worksheet.set_column(0, 0, max_len)

        # Crear formato para la columna índice sin negrita, sin centrado y sin bordes
        index_format = workbook.add_format({'align': 'left', 'bold': False, 'border': 0})

        # Escribir el nombre del índice (si existe) con el formato deseado
        if df.index.name:
            worksheet.write(0, 0, df.index.name, index_format)
        else:
            worksheet.write(0, 0, '', index_format)

        # Escribir los valores del índice (nombres de los estudiantes) con el formato deseado
        for row_num, value in enumerate(df.index.values):
            worksheet.write(row_num + 1, 0, value, index_format)

        # Formato para notas: mostrar siempre una decimal
        grade_format = workbook.add_format({'num_format': '0.0'})

        # Aplicar el formato a las columnas de notas
        for idx, col in enumerate(df.columns):
            if col not in ['Rut', 'Email', 'Curso']:
                # Aplicar el formato solo a las columnas de notas
                worksheet.set_column(idx + 1, idx + 1, None, grade_format)

    processed_data = output.getvalue()
    return processed_data

def main():
    st.title('Buscar notas por curso en Canvas')

    # Inicializar variables de estado
    if 'button_clicked' not in st.session_state:
        st.session_state['button_clicked'] = False
    if 'course_ids' not in st.session_state:
        st.session_state['course_ids'] = []
    if 'dataframes' not in st.session_state:
        st.session_state['dataframes'] = {}
    if 'course_names' not in st.session_state:
        st.session_state['course_names'] = {}

    input_ids = st.text_input('Ingresa uno o varios IDs de cursos:', '')

    def process_input():
        if input_ids:
            course_ids = input_ids.replace(',', ' ').replace('\n', ' ').split()
            course_ids = [cid.strip() for cid in course_ids if cid.strip()]
            st.session_state['course_ids'] = course_ids
            st.session_state['button_clicked'] = True
            st.session_state['dataframes'] = {}
            st.session_state['course_names'] = {}
            for course_id in course_ids:
                info = course_info(course_id)
                course_name = info.get("name", "Desconocido") if info else "Desconocido"
                st.session_state['course_names'][course_id] = course_name
                try:
                    df = obtener_notas_curso(course_id)
                    if df is not None:
                        st.session_state['dataframes'][course_id] = df
                except Exception as e:
                    st.error(f'Error al obtener las notas para el curso {course_id}: {e}')
        else:
            st.warning('Por favor ingresa un ID de curso válido.')

    st.button('Buscar Notas', on_click=process_input)

    if st.session_state.get('button_clicked'):
        for course_id in st.session_state['course_ids']:
            course_name = st.session_state['course_names'].get(course_id, 'Desconocido')
            df = st.session_state['dataframes'].get(course_id)
            if df is not None:
                df_missing_grades = df[df.applymap(lambda x: pd.isnull(x)).any(axis=1)]
                if not df_missing_grades.empty:
                    st.header(':red[ESTE CURSO TIENE NOTAS PENDIENTES DE LOS SIGUIENTES ALUMNOS 😭]')
                    st.subheader(f'{course_name} ({course_id})', divider='red')
                    st.dataframe(df_missing_grades, use_container_width=True)
                else:
                    st.header(':green[ESTE CURSO TIENE TODAS SUS NOTAS!!!] 🤩')
                    st.subheader(f'{course_name} ({course_id})', divider='green')
                    st.dataframe(df, use_container_width=True)
                    columnas_necesarias = ['Rut', 'Email', 'Nota']
                    filtered_dataframe = df.loc[:, columnas_necesarias]
                    nombre_curso = f"{course_name}"  # Cambia el nombre del curso según necesites
                    filtered_dataframe.insert(2, 'Curso', nombre_curso)
                    excel_data = to_excel(filtered_dataframe)
                    st.download_button(
                        label="Descargar Reporte",
                        data=excel_data,
                        file_name=f"{course_name} - {course_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_{course_id}"  # Clave única para cada botón
                    )
            else:
                st.warning(f'No se encontraron calificaciones para el curso {course_id}')

if __name__ == '__main__':
    main()