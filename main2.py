import streamlit as st
import requests
import pandas as pd
from decouple import config

API_URL = 'https://canvas.uautonoma.cl/api/v1'
ACCESS_TOKEN = config('TOKEN')  # Reemplaza con tu token de acceso

st.set_page_config(page_title="Grades Wizard", layout="wide", page_icon="🚀" )

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
    student_ids = [s['id'] for s in students if not s['name'] == 'Estudiante de prueba']
    student_names = {s['id']: s['name'] for s in students if not s['name'] == 'Estudiantes de prueba'}

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
        final_grade = grades.get('final_grade', '-')  # Nota final en formato de letra
        final_score = grades.get('final_score', '-')  # Nota final en formato numérico
        final_scores[user_id] = str(final_score) + '%'
        final_grades[user_id] = final_grade

    # Configurar los parámetros de la solicitud para las submissions
    url = f'{API_URL}/courses/{COURSE_ID}/students/submissions'
    params = {
        'include[]': 'sub_assignment_submissions',
        'exclude_response_fields[]': ['preview_url', 'external_tool_url', 'url', 'attachments', 'attempt', 'cached_due_date','sticker', 'submitted_at','redo_request', 'late_policy_status', 'late', 'points_deducted', 'posted_at','proxy_submitter','proxy_submitter_id','seconds_late','excused', 'grading_period_id','grade_matches_current_submission',],
        'grouped': 1,
        'response_fields[]': [
            'assignment_id', 
            'custom_grade_status_id', 'entered_grade', 'entered_score',
            'grade','id', 'missing', 'score', 'submission_type', 'user_id','workflow_state'
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
        student_name = student_names.get(student_id, 'Desconocido')
        student_sis_user_id = student.get('sis_user_id', 'Desconocido')
        rut = student_sis_user_id[:-1] + '-' + student_sis_user_id[-1]
        student_email = user_emails.get(student_id, 'Desconocido')
        row = {'Estudiante': student_name, 'Rut': rut, 'Email':student_email}
        for submission in student['submissions']:
            assignment_id = submission['assignment_id']
            assignment_name = assignment_names.get(assignment_id, f'Tarea {assignment_id}')
            grade = submission.get('grade')
            grade = grade if grade else "❌"
            row[assignment_name] = grade
        # Agregar las notas finales al registro
        row['Nota'] = final_grades.get(student_id, '❌')
        row['Porcentaje'] = final_scores.get(student_id, '❌')
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
        print(f"Error al obtener informacion del curso {COURSE_ID}: {response.status_code}")
        return None

#NO SE ESTA OCUPANDO POR AHORA
def missing_data(val):
    color = 'background-color: #ff4b4b' if val == '❌' else ''
    return color

def main():
    st.title('Buscar notas por curso en Canvas')

    # st.write('Ingresa uno o varios IDs de cursos:')

    input_ids = st.text_input('Ingresa uno o varios IDs de cursos:', '')

    if st.button('Buscar Notas'):
        if input_ids:
            course_ids = input_ids.replace(',', ' ').replace('\n', ' ').split()
            course_ids = [cid.strip() for cid in course_ids if cid.strip()]
            for course_id in course_ids:
                info = course_info(course_id)
                course_name = info.get("name", "Desconocido")
                # st.header(f'{course_name} ({course_id})')
                try:
                    df = obtener_notas_curso(course_id)
                    df_missing_grades = df[df.map(lambda x: x == '❌').any(axis=1)]
                    if df is not None:
                        if not df_missing_grades.empty:
                            st.header(':red[ESTE CURSO TIENE NOTAS PENDIENTES DE LOS SIGUIENTES ALUMNOS 😭]')
                            st.subheader(f'{course_name} ({course_id})', divider='red')
                            # st.dataframe(df_missing_grades.style.applymap(missing_data), use_container_width=True)
                            st.dataframe(df_missing_grades, use_container_width=True)
                        else:
                            st.header(':green[ESTE CURSO TIENE TODAS SUS NOTAS!!!] 🤩')
                            st.subheader(f'{course_name} ({course_id})', divider='green')
                            st.dataframe(df, use_container_width=True)
                except Exception as e:
                    st.error(f'Error al obtener las notas para el curso {course_id}: {e}')
        else:
            st.warning('Por favor ingresa un ID de curso valido.')

if __name__ == '__main__':
    main()