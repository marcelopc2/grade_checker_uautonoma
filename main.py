import streamlit as st
import requests
import pandas as pd
from decouple import config
from io import BytesIO
import time
import unicodedata

API_URL = config('URL')
ACCESS_TOKEN = config('TOKEN')

st.set_page_config(page_title="Grades Wizard", layout="wide", page_icon="🚀")

headers = {
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}

def spanish_sort_key(name):
    name = name.upper()
    name = ''.join((c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn'))
    name = name.replace('Ñ', 'N~')
    return name

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

    # Filtrar estudiantes y crear diccionarios
    student_ids = [s['id'] for s in students if s['name'] != 'Estudiante de prueba']
    student_names = {s['id']: s['name'] for s in students if s['name'] != 'Estudiante de prueba'}
    student_sortable_names = {s['id']: s['sortable_name'] for s in students if s['name'] != 'Estudiante de prueba'}
    user_emails = {s['id']: s.get('login_id', 'Desconocido') for s in students if s['name'] != 'Estudiante de prueba'}

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

    # Crear una estructura inicial del DataFrame con los estudiantes
    data = []
    for student_id in student_ids:
        student_name = student_names.get(student_id, 'Desconocido').title()
        student_sortable_name = student_sortable_names.get(student_id, 'Desconocido')
        student_email = user_emails.get(student_id, 'Desconocido').lower()
        row = {
            'Estudiante': student_name,
            'Email': student_email,
            'SortableName': student_sortable_name
        }
        data.append(row)

    df = pd.DataFrame(data)
    df = df.set_index('Estudiante')

    # Para cada tarea, obtener las submissions y actualizar el DataFrame
    for assignment in assignments:
        assignment_id = assignment['id']
        assignment_name = assignment['name']
        url = f'{API_URL}/courses/{COURSE_ID}/assignments/{assignment_id}/submissions'
        params = {'per_page': 100}
        submissions = []
        while url:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                st.error(f'Error al obtener submissions de la tarea {assignment_name} ({assignment_id}): {response.text}')
                return None
            submissions.extend(response.json())
            url = response.links.get('next', {}).get('url')

        # Actualizar el DataFrame con las notas de cada submission
        for submission in submissions:
            student_id = submission['user_id']
            grade = submission.get('grade')
            if grade is not None:
                try:
                    grade = float(grade)
                except ValueError:
                    pass
            else:
                grade = None
            student_name = student_names.get(student_id, 'Desconocido').title()
            if student_name in df.index:
                df.at[student_name, assignment_name] = grade

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
    user_ruts = {}
    for enrollment in enrollments:
        user_id = enrollment['user_id']
        grades = enrollment.get('grades', {})
        user_sis_user_id = enrollment['user'].get('sis_user_id', 'Desconocido')
        if user_sis_user_id != 'Desconocido':
            rut = user_sis_user_id[:-1] + '-' + user_sis_user_id[-1]
        else:
            rut = 'Desconocido'
        user_ruts[user_id] = rut
        final_grade = grades.get('final_grade')  
        final_score = grades.get('final_score') 
        try:
            final_grades[user_id] = float(final_grade) if final_grade is not None else None
        except (ValueError, TypeError):
            final_grades[user_id] = None
        final_scores[user_id] = f"{final_score}%" if final_score is not None else None

    # Agregar las notas finales y RUT al DataFrame
    for student_id in student_ids:
        student_name = student_names.get(student_id, 'Desconocido').title()
        if student_name in df.index:
            df.at[student_name, 'Rut'] = user_ruts.get(student_id, 'Desconocido')
            df.at[student_name, 'Porcentaje'] = final_scores.get(student_id)
            if final_grades.get(student_id) is not None:
                df.at[student_name, 'Nota UAC'] = final_grades.get(student_id)
            else:
                df.at[student_name, 'Nota UAC'] = "Sin Nota"

    # Función para convertir porcentaje a número (elimina el % y convierte a float)
    def parse_percentage(percentage):
        if isinstance(percentage, str) and percentage.endswith('%'):
            try:
                return float(percentage[:-1])
            except ValueError:
                return None
        return None

    # Mapeo exacto para la escala Portugal (IEES)
    def get_nota_portugal(porcentaje):
        if porcentaje is None:
            return "Sin Nota"
        
        # Tabla exacta de conversión
        portugal_scale = {
            0: 0.0, 1: 0.2, 2: 0.3, 3: 0.5, 4: 0.7, 5: 0.8,
            6: 1.0, 7: 1.2, 8: 1.3, 9: 1.5, 10: 1.7, 11: 1.8,
            12: 2.0, 13: 2.2, 14: 2.3, 15: 2.5, 16: 2.7, 17: 2.8,
            18: 3.0, 19: 3.2, 20: 3.3, 21: 3.5, 22: 3.7, 23: 3.8,
            24: 4.0, 25: 4.2, 26: 4.3, 27: 4.5, 28: 4.7, 29: 4.8,
            30: 5.0, 31: 5.2, 32: 5.3, 33: 5.5, 34: 5.7, 35: 5.8,
            36: 6.0, 37: 6.2, 38: 6.3, 39: 6.5, 40: 6.7, 41: 6.8,
            42: 7.0, 43: 7.2, 44: 7.3, 45: 7.5, 46: 7.7, 47: 7.8,
            48: 8.0, 49: 8.2, 50: 8.3, 51: 8.5, 52: 8.7, 53: 8.8,
            54: 9.0, 55: 9.2, 56: 9.3, 57: 9.5, 58: 9.7, 59: 9.8,
            60: 10.0, 61: 10.3, 62: 10.5, 63: 10.8, 64: 11.0,
            65: 11.3, 66: 11.5, 67: 11.8, 68: 12.0, 69: 12.3,
            70: 12.5, 71: 12.8, 72: 13.0, 73: 13.3, 74: 13.5,
            75: 13.8, 76: 14.0, 77: 14.3, 78: 14.5, 79: 14.8,
            80: 15.0, 81: 15.3, 82: 15.5, 83: 15.8, 84: 16.0,
            85: 16.3, 86: 16.5, 87: 16.8, 88: 17.0, 89: 17.3,
            90: 17.5, 91: 17.8, 92: 18.0, 93: 18.3, 94: 18.5,
            95: 18.8, 96: 19.0, 97: 19.3, 98: 19.5, 99: 19.8,
            100: 20.0
        }
        
        # Redondear el porcentaje al entero más cercano
        porcentaje_entero = round(porcentaje)
        return portugal_scale.get(porcentaje_entero, "Sin Nota")

    # Aplicar las escalas de notas
    for student_name in df.index:
        porcentaje = parse_percentage(df.at[student_name, 'Porcentaje'])
        
        if porcentaje is not None:
            # Escala Paraguay (UAP)
            if porcentaje < 60:
                df.at[student_name, 'Nota UAP'] = 1
            elif 60 <= porcentaje < 70:
                df.at[student_name, 'Nota UAP'] = 2
            elif 70 <= porcentaje < 80:
                df.at[student_name, 'Nota UAP'] = 3
            elif 80 <= porcentaje < 90:
                df.at[student_name, 'Nota UAP'] = 4
            else:
                df.at[student_name, 'Nota UAP'] = 5
            
            # Escala Portugal (IEES) - usando la tabla exacta
            df.at[student_name, 'Nota IEES'] = get_nota_portugal(porcentaje)
            
            # Escala Carver
            if porcentaje < 60:
                df.at[student_name, 'Nota Carver'] = 0
            elif 60 <= porcentaje < 65:
                df.at[student_name, 'Nota Carver'] = 1.0
            elif 65 <= porcentaje < 70:
                df.at[student_name, 'Nota Carver'] = 1.5
            elif 70 <= porcentaje < 75:
                df.at[student_name, 'Nota Carver'] = 2.0
            elif 75 <= porcentaje < 80:
                df.at[student_name, 'Nota Carver'] = 2.5
            elif 80 <= porcentaje < 85:
                df.at[student_name, 'Nota Carver'] = 3.0
            elif 85 <= porcentaje < 90:
                df.at[student_name, 'Nota Carver'] = 3.5
            elif 90 <= porcentaje < 95:
                df.at[student_name, 'Nota Carver'] = 3.75
            else:
                df.at[student_name, 'Nota Carver'] = 4.0
        else:
            df.at[student_name, 'Nota UAP'] = "Sin Nota"
            df.at[student_name, 'Nota IEES'] = "Sin Nota"
            df.at[student_name, 'Nota Carver'] = "Sin Nota"

    # Ordenar los estudiantes de forma alfabética
    df = df.sort_values('SortableName', key=lambda x: x.apply(spanish_sort_key))
    df = df.drop(columns=['SortableName'])

    # Eliminar la columna 'Autoevaluación' si existe
    df = df.drop(columns='Autoevaluación') if 'Autoevaluación' in df.columns else df

    if df.empty:
        st.warning(f'No se encontraron calificaciones para el curso {COURSE_ID}')
        return None

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
        # Escribe el DataFrame completo
        df.to_excel(writer, sheet_name='Calificaciones', index=True, header=True)
        workbook  = writer.book
        worksheet = writer.sheets['Calificaciones']
        
        # Formatos base
        border_format       = workbook.add_format({'border': 1})
        integer_format      = workbook.add_format({'num_format': '0',    'border': 1})
        one_decimal_format  = workbook.add_format({'num_format': '0.0',  'border': 1})
        two_decimals_format = workbook.add_format({'num_format': '0.00', 'border': 1})
        header_format       = workbook.add_format({'border': 1, 'bold': True})
        index_format        = workbook.add_format({'align': 'left', 'border': 1})
        
        # Helper para decimales
        def needs_two_decimals(value):
            try:
                return round(value, 2) != round(value, 1)
            except:
                return False
        
        # Formatear columnas de datos (todas excepto el índice)
        for col_num, column_name in enumerate(df.columns, start=1):
            # Ajustar ancho de columna
            max_len = max(
                df[column_name].astype(str).map(len).max(),
                len(str(column_name))
            ) + 2
            worksheet.set_column(col_num, col_num, max_len)
            
            # Encabezado
            worksheet.write(0, col_num, column_name, header_format)
            
            # Celdas
            for row_num, value in enumerate(df[column_name], start=1):
                if column_name == 'Nota UAP':
                    worksheet.write(row_num, col_num, value, integer_format)
                elif column_name == 'Nota Carver':
                    fmt = two_decimals_format if needs_two_decimals(value) else one_decimal_format
                    worksheet.write(row_num, col_num, value, fmt)
                elif column_name in ['Nota UAC', 'Nota IEES']:
                    worksheet.write(row_num, col_num, value, one_decimal_format)
                else:
                    worksheet.write(row_num, col_num, value, border_format)
        
        # ---- Índice (columna A) ----
        # 1) Calcular ancho sin aplicar formato de borde aquí
        ancho_indice = max(
            df.index.astype(str).map(len).max(),
            len(str(df.index.name or ''))
        ) + 2
        worksheet.set_column(0, 0, ancho_indice)
        
        # 2) Escribir título de índice
        worksheet.write(0, 0, df.index.name or '', header_format)
        
        # 3) Escribir cada valor de índice con formato
        for row_num, idx_val in enumerate(df.index, start=1):
            worksheet.write(row_num, 0, idx_val, index_format)
    
    return output.getvalue()

def main():
    st.title('Generador de Reportes de Notas 🚀')
    st.info(
        """
        Genera reportes de notas de cursos en **Canvas LMS** con opcion de descarga en Excel.
        - Agregada escala UAP, IEES, Carver. 

        **Última actualización:** 23-04-2025
        """
    )

    input_ids = st.text_input('Ingresa uno o varios IDs de cursos:', '')
    
    st.markdown('**Selecciona las escalas de nota a mostrar:**')
    col1, col2, col3, col4, _ = st.columns([1, 1, 1, 1, 5])
    with col1:
        show_uac = st.checkbox('Nota UAC', value=True)
    with col2:
        show_uap = st.checkbox('Nota UAP', value=True)
    with col3:
        show_iees = st.checkbox('Nota IEES', value=True)
    with col4:
        show_carver = st.checkbox('Nota Carver', value=True)
    selected_scales = [
        escala for escala, visible in [
            ('Nota UAC',    show_uac),
            ('Nota UAP',    show_uap),
            ('Nota IEES',   show_iees),
            ('Nota Carver', show_carver),
        ] if visible
    ]

    def process_input():
        if not input_ids:
            st.warning('Por favor ingresa un ID de curso válido.')
            return
        st.session_state['start_time'] = time.time()
        course_ids = input_ids.replace(',', ' ').replace('\n', ' ').split()
        st.session_state['course_ids'] = [cid.strip() for cid in course_ids if cid.strip()]
        st.session_state['button_clicked'] = True
        st.session_state['dataframes'] = {}
        st.session_state['course_names'] = {}
        st.session_state['sis_courses_ids'] = {}

        for course_id in st.session_state['course_ids']:
            info = course_info(course_id)
            course_name = info.get("name", "Desconocido") if info else "Desconocido"
            course_sis_id = info.get('sis_course_id', "Desconocido") if info else "Desconocido"
            st.session_state['course_names'][course_id] = course_name
            st.session_state['sis_courses_ids'][course_id] = course_sis_id
            try:
                df = obtener_notas_curso(course_id)
                if df is not None:
                    st.session_state['dataframes'][course_id] = df
            except Exception as e:
                st.error(f'Error al obtener las notas para el curso {course_id}: {e}')

    st.button('Buscar Notas', on_click=process_input)

    # 3) MOSTRAR RESULTADOS FILTRANDO COLUMNAS
    if st.session_state.get('button_clicked'):
        for course_id in st.session_state['course_ids']:
            df = st.session_state['dataframes'].get(course_id)
            course_name = st.session_state['course_names'].get(course_id, 'Desconocido')
            course_sis_id = st.session_state['sis_courses_ids'].get(course_id, 'Desconocido')

            if 'start_time' in st.session_state:
                elapsed_time = time.time() - st.session_state['start_time']
                st.write(f"⏱️ Tiempo de procesamiento: {elapsed_time:.2f} segundos")
                del st.session_state['start_time']

            if df is None or df.empty:
                st.warning(f'No se encontraron calificaciones para el curso {course_id}')
                continue

            # Columnas de escalas y filtrado según selección
            scale_cols = ['Nota UAC', 'Nota UAP', 'Nota IEES', 'Nota Carver']
            cols_to_show = [
                c for c in df.columns
                if not (c in scale_cols and c not in selected_scales)
            ]

            # Detectar filas con notas faltantes
            df_missing = df[df.isna().any(axis=1)]

            if df_missing.empty:
                st.header(':green[ESTE CURSO TIENE TODAS SUS NOTAS!!!] 🤩')
                st.subheader(f'{course_name} ({course_id})', divider='green')

                df_display = df[cols_to_show]
                st.dataframe(df_display, use_container_width=True)

                # Métricas
                numeric_values = pd.to_numeric(df['Nota UAC'], errors='coerce')
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Promedio UAC",    f"{round(numeric_values.mean(),1)}")
                col2.metric("Promedio UAP",    f"{round(df['Nota UAP'].mean(),2)}")
                col3.metric("Promedio IEES",   f"{round(df['Nota IEES'].mean(),1)}")
                col4.metric("Promedio Carver", f"{round(df['Nota Carver'].mean(),2)}")

                # Preparar Excel con solo las columnas seleccionadas + Rut, Email, Curso
                base_cols = ['Rut', 'Email']
                excel_cols = base_cols + selected_scales
                filtered_df = df.loc[:, excel_cols]
                filtered_df.insert(2, 'Curso', course_name)

                excel_data = to_excel(filtered_df)
                st.download_button(
                    label="Descargar Reporte",
                    data=excel_data,
                    file_name=f"{course_id}_{course_name}_{course_sis_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"download_{course_id}"
                )
            else:
                st.header(':red[ESTE CURSO TIENE NOTAS PENDIENTES 😭]')
                st.subheader(f'{course_name} ({course_id})', divider='red')

                df_display = df_missing[cols_to_show].fillna('❌')
                st.dataframe(df_display, use_container_width=True)

                st.warning("Faltan notas → no disponible descarga.")

if __name__ == '__main__':
    main()